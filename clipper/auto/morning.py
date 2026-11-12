#!/usr/bin/env python3
"""Jarvis morning run: pull new clips -> AI picks + hooks (Brand Brain) -> cut -> quality check -> Clip Studio drafts -> text summary.
   ~/Projects/clipper/.venv/bin/python ~/Projects/clipper/auto/morning.py [--skip-fetch BATCH]
"""
import datetime, json, os, re, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from notify import send
from gemini import ask_json
PY = os.path.join(ROOT, '.venv', 'bin', 'python')
HUB_BATCH = os.path.expanduser('~/Projects/post-hub/batches')
DIR2PAGE = {'pulsevice': 'pulsevice', 'vicecityrp': 'vicecityrp', 'physix': 'gta6physix', 'kai': 'kai', 'adin': 'adin', 'n3on': 'n3on'}
AUTO = {'pulsevice', 'vicecityrp', 'gta6physix'}   # pages that schedule themselves (no approval needed)
WANT = {'pulsevice': 4, 'vicecityrp': 4, 'gta6physix': 4, 'kai': 2, 'adin': 2, 'n3on': 2}   # drafts per morning
LOG = open(os.path.join(HERE, 'morning.log'), 'a')

def log(*a):
    print(*a, flush=True); print(datetime.datetime.now().strftime('%H:%M'), *a, file=LOG, flush=True)

def brain(page):
    return open(os.path.join(ROOT, 'brain', '_shared.md')).read() + '\n' + open(os.path.join(ROOT, 'brain', page + '.md')).read()

def pick(page, index_txt, n):
    prompt = f"""You pick and title short-form clips for a TikTok clip page. Follow these page rules exactly:
{brain(page)}

Below are today's raw clips (number | streamer | views | length | title, then the transcript with [start-end] seconds).
Choose up to {n} clips that will do best (fewer if the rest are weak or break the rules). For each give a trim inside the clip.
Return JSON: {{"picks":[{{"clip":"07","start":1.0,"end":30.0,"hook":"...","caption":"... #tags","why":"short reason"}}],
"skipped":"one short sentence on what you skipped and why"}}

RAW CLIPS:
{index_txt[:60000]}"""
    return ask_json(prompt)

def main():
    args = sys.argv[1:]
    batch = args[1] if args[:1] == ['--skip-fetch'] else 'auto-' + datetime.date.today().strftime('%Y%m%d')
    problems, made = [], {}
    if args[:1] != ['--skip-fetch']:
        log('fetch', batch)
        r = subprocess.run(['nice', '-n', '10', PY, os.path.join(ROOT, 'fetch.py'), batch], capture_output=True, text=True)
        open(os.path.join(HERE, 'fetch.log'), 'a').write(r.stdout + r.stderr)
        if 'BATCH DONE' not in r.stdout: problems.append('clip download step crashed (see auto/fetch.log)')
    work = os.path.join(ROOT, 'work', batch); jobs, picks_meta = [], []
    for d, page in DIR2PAGE.items():
        idx = os.path.join(work, d, 'index.txt')
        if not os.path.exists(idx): problems.append(f'{page}: no new clips found'); continue
        try: res = pick(page, open(idx).read(), WANT[page])
        except Exception as e: problems.append(f'{page}: AI picker failed ({str(e)[:80]})'); continue
        meta = {}
        for line in open(idx):
            m = re.match(r'^## (\d+) \| (\S+) \| (\d+) views', line)
            if m: meta[m.group(1)] = (m.group(2), int(m.group(3)))
        for i, p in enumerate(res.get('picks', [])):
            c = str(p.get('clip', '')).zfill(2); src = os.path.join(work, d, c + '.mp4')
            try: s, e = float(p['start']), float(p['end'])
            except Exception: continue
            if not os.path.exists(src) or not (10 <= e - s <= 50): continue
            slug = re.sub(r'[^a-z0-9]+', '_', p.get('hook', 'clip').lower())[:28].strip('_')
            out = os.path.join(ROOT, 'out', batch, page, f'{i + 1:02d}_{slug}.mp4')
            jobs.append({'src': src, 'words': os.path.join(work, d, c + '.words.json'), 'start': s, 'end': e,
                         'hook': p.get('hook', ''), 'out': out, 'layout': 'full', 'cx': 0.5})
            picks_meta.append({'file': out, 'page': page, 'caption': p.get('caption', ''), 'hook': p.get('hook', ''),
                               'source': meta.get(c, ('?', 0))[0], 'views': meta.get(c, ('?', 0))[1]})
        log(page, len(res.get('picks', [])), 'picked |', res.get('skipped', ''))
    if jobs:
        jf = os.path.join(work, 'auto_jobs.json'); json.dump(jobs, open(jf, 'w'), indent=1)
        r = subprocess.run(['nice', '-n', '10', PY, os.path.join(ROOT, 'split.py'), jf], capture_output=True, text=True, cwd=ROOT)
        LOG.write(r.stdout[-3000:] + r.stderr[-2000:])
        picks_meta = [p for p in picks_meta if os.path.exists(p['file'])]
        pf = os.path.join(work, 'auto_picks.json'); json.dump(picks_meta, open(pf, 'w'), indent=1)
        r = subprocess.run(['python3', os.path.join(HUB_BATCH, 'studio_push.py'), pf], capture_output=True, text=True)
        LOG.write(r.stdout[-3000:] + r.stderr[-2000:])
        for ln in r.stdout.splitlines():
            if ln.startswith('DRAFTED'): made[ln.split()[1]] = made.get(ln.split()[1], 0) + 1
            if ln.startswith(('REJECTED', 'UPLOAD FAILED', 'DRAFT FAILED')): problems.append(ln[:90])
    scheduled = {}
    if made:   # auto-approve fresh drafts on AUTO pages -> next open posting slot
        import urllib.request
        hub = 'https://post-hub-nine.vercel.app'; key = open(os.path.expanduser('~/.posthub_key')).read().strip()
        hdr = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key, 'Origin': hub}
        try:
            drafts = json.load(urllib.request.urlopen(urllib.request.Request(hub + '/api/studio', headers=hdr), timeout=120)).get('drafts', [])
            for dft in drafts:
                if dft.get('page') not in AUTO: continue
                r = json.load(urllib.request.urlopen(urllib.request.Request(hub + '/api/studio', data=json.dumps({'action': 'approve', 'postId': dft['id']}).encode(), headers=hdr), timeout=120))
                if r.get('ok'): scheduled[dft['page']] = scheduled.get(dft['page'], 0) + 1
                else: problems.append(f"{dft['page']}: couldn't auto-schedule ({r.get('error', '')[:40]})")
        except Exception as e: problems.append(f'auto-schedule failed ({str(e)[:60]})')
    total = sum(made.values())
    lines = [f"🎬 {sum(scheduled.values())} new clips scheduled automatically"]
    lines += [f"• {k}: {v} scheduled" for k, v in sorted(scheduled.items())]
    held = {k: v for k, v in made.items() if k not in AUTO}
    if held: lines.append('Saved as drafts (pages still warming): ' + ', '.join(f'{k} {v}' for k, v in sorted(held.items())))
    if problems: lines.append('⚠️ ' + '; '.join(problems[:5]))
    send('\n'.join(lines)); log('done', total, problems)

if __name__ == '__main__':
    try: main()
    except Exception:
        send('⚠️ Jarvis morning run crashed: ' + traceback.format_exc()[-300:]); raise

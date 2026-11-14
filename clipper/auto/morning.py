#!/usr/bin/env python3
"""Jarvis morning run: pull new clips -> AI picks + hooks (Brand Brain) -> cut -> quality check -> Clip Studio drafts -> text summary.
   ~/Projects/clipper/.venv/bin/python ~/Projects/clipper/auto/morning.py [--skip-fetch BATCH]
"""
import datetime, json, os, re, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from notify import send, status
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

def recent_posts(page):
    """Captions this page already posted/scheduled, so the AI doesn't repeat a story told by another clipper."""
    import urllib.request
    try:
        acc = {'pulsevice': 'cmwcu0zfb008w01lm4h5gv59d', 'vicecityrp': 'cmwcw1agy009501lmehe4420r', 'gta6physix': 'cmwcw8bo5009601lmexy736z1',
               'kai': 'cmwcvr8px009401lmtfla7j8u', 'adin': 'cmwcvc7ar009101lma8hncs5e', 'n3on': 'cmwcu6hns008x01lm6udwhqus'}[page]
        key = open(os.path.expanduser('~/.posthub_key')).read().strip(); out = []
        for stt in ('SCHEDULED', 'COMPLETED', 'DRAFT'):
            d = json.load(urllib.request.urlopen(urllib.request.Request(f'https://post-hub-nine.vercel.app/api/posts?status={stt}', headers={'Authorization': 'Bearer ' + key}), timeout=60))
            out += [p.get('text', '')[:90] for p in d.get('posts', []) if (p.get('platforms') or [{}])[0].get('connectionId') == acc]
        return out[:40]
    except Exception: return []


def has_burned_captions(src, s, e, words_path=None):
    """OCR 3 frames from the bottom of the source. If the on-screen text matches the words being spoken, the clip already has subtitles."""
    import shutil, tempfile
    if not shutil.which('tesseract'): return False
    spoken = set()
    try: spoken = {w['w'].lower().strip('.,!?') for w in json.load(open(words_path)) if w['e'] > s - 1 and w['s'] < e + 1 and len(w['w'].strip('.,!?')) >= 3}
    except Exception: pass
    hits = 0
    for k in (0.3, 0.55, 0.8):
        t = s + (e - s) * k; img = tempfile.mktemp(suffix='.png')
        subprocess.run([os.path.expanduser('~/.local/bin/ffmpeg'), '-y', '-loglevel', 'error', '-ss', str(t), '-i', src, '-frames:v', '1',
                        '-vf', 'crop=iw:ih*0.42:0:ih*0.58,scale=iw*2:-1,format=gray', img])
        out = subprocess.run(['tesseract', img, '-', '--psm', '11'], capture_output=True, text=True).stdout.lower()
        seen = set(re.findall(r'[a-z]{3,}', out))
        if (len(seen & spoken) >= 2) if spoken else (len(seen) >= 4): hits += 1
    return hits >= 2

def pick(page, index_txt, n):
    prompt = f"""You pick and title short-form clips for a TikTok clip page. Follow these page rules exactly:
{brain(page)}

ALREADY POSTED on this page (do NOT pick a clip about the same moment/story, even from a different clipper):\n{chr(10).join('- ' + c for c in recent_posts(page)) or '- (none)'}\n\nBelow are today's raw clips (number | streamer | views | length | title, then the transcript with [start-end] seconds).
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
    status('chief', 'working', 'Daily run started'); status('research', 'working', 'Pulling new clips from the streamers…')
    if args[:1] != ['--skip-fetch']:
        log('fetch', batch)
        r = subprocess.run(['nice', '-n', '10', PY, os.path.join(ROOT, 'fetch.py'), batch], capture_output=True, text=True)
        open(os.path.join(HERE, 'fetch.log'), 'a').write(r.stdout + r.stderr)
        if 'BATCH DONE' not in r.stdout: problems.append('clip download step crashed (see auto/fetch.log)')
    work = os.path.join(ROOT, 'work', batch); jobs, picks_meta = [], []
    nraw = sum(len([f for f in fs if f.endswith('.words.json')]) for _, _, fs in os.walk(work)) if os.path.isdir(work) else 0
    status('research', 'done' if nraw else 'error', f'{nraw} new clips pulled + transcribed'); status('writers', 'working', 'Reading transcripts, picking the best moments…')
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
            burned = has_burned_captions(src, s, e, os.path.join(work, d, c + '.words.json'))
            if burned: log(page, c, 'already has captions -> hook only')
            jobs.append({'src': src, 'words': '' if burned else os.path.join(work, d, c + '.words.json'), 'start': s, 'end': e,
                         'hook': p.get('hook', ''), 'out': out, 'layout': 'full', 'cx': 0.5})
            picks_meta.append({'file': out, 'page': page, 'caption': p.get('caption', ''), 'hook': p.get('hook', ''),
                               'source': meta.get(c, ('?', 0))[0], 'views': meta.get(c, ('?', 0))[1]})
        log(page, len(res.get('picks', [])), 'picked |', res.get('skipped', ''))
    status('writers', 'done', f'{len(picks_meta)} clips picked, hooks + captions written')
    if jobs:
        status('edit', 'working', f'Cutting {len(jobs)} clips…')
        jf = os.path.join(work, 'auto_jobs.json'); json.dump(jobs, open(jf, 'w'), indent=1)
        r = subprocess.run(['nice', '-n', '10', PY, os.path.join(ROOT, 'split.py'), jf], capture_output=True, text=True, cwd=ROOT)
        LOG.write(r.stdout[-3000:] + r.stderr[-2000:])
        picks_meta = [p for p in picks_meta if os.path.exists(p['file'])]
        status('edit', 'done', f'{len(picks_meta)} clips cut (9:16, blurred edges, captions)'); status('qa', 'working', 'Checking frames, audio, length…')
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
    status('qa', 'done', f'{sum(made.values())} clips passed quality checks')
    status('distribution', 'done', f'{sum(scheduled.values())} clips scheduled automatically')
    total = sum(made.values())
    lines = [f"🎬 {sum(scheduled.values())} new clips scheduled automatically"]
    lines += [f"• {k}: {v} scheduled" for k, v in sorted(scheduled.items())]
    held = {k: v for k, v in made.items() if k not in AUTO}
    if held: lines.append('Saved as drafts (pages still warming): ' + ', '.join(f'{k} {v}' for k, v in sorted(held.items())))
    if problems: lines.append('⚠️ ' + '; '.join(problems[:5]))
    send('\n'.join(lines)); log('done', total, problems)
    status('chief', 'error' if problems else 'done', ('⚠️ ' + problems[0]) if problems else f'All good — {sum(scheduled.values())} new clips scheduled')

if __name__ == '__main__':
    try: main()
    except Exception:
        send('⚠️ Jarvis morning run crashed: ' + traceback.format_exc()[-300:]); raise

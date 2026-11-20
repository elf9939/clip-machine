#!/usr/bin/env python3
"""FAST MODE: one clip at a time, straight into Clip Studio the moment it's done (no hour-long batch).
Round-robin across pages until each has TARGET clips. Every clip: download -> transcribe -> AI judges THIS clip -> cut + animated mascot -> draft.
  ~/Projects/clipper/.venv/bin/python stream.py [target_per_page]
"""
import json, os, subprocess, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'auto'))
src = open(os.path.join(HERE, 'fetch.py')).read(); F = {'__file__': os.path.join(HERE, 'fetch.py')}
exec(src[:src.index('def gaps_ok')], F)                     # reuse the GTA 6 source lists + filters
from split import render
from gemini import ask_json
from faster_whisper import WhisperModel

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 3
ORDER = ['physix', 'pulsevice', 'n3on', 'adin', 'kai', 'vicecityrp']
PAUSED = {'adin', 'physix'}   # physix: TikTok restricted Nov 19 (every post 0 views)   # Nov 19: all 7 recent Adin TikToks restricted — no new clips until we know why
ORDER = [d for d in ORDER if d not in PAUSED]
if os.environ.get('STREAM_PAGES'): ORDER = [d for d in ORDER if d in os.environ['STREAM_PAGES'].split(',')]   # cloud: each runner takes some pages
STOP_AT = time.time() + 60 * float(os.environ.get('STREAM_MINUTES') or 1e6)   # cloud: stop starting new clips before the time limit
PAGEKEY = {'physix': 'gta6physix'}
ACCT = {'pulsevice': 'cmwcu0zfb008w01lm4h5gv59d', 'vicecityrp': 'cmwcw1agy009501lmehe4420r', 'gta6physix': 'cmwcw8bo5009601lmexy736z1',
        'kai': 'cmwcvr8px009401lmtfla7j8u', 'adin': 'cmwcvc7ar009101lma8hncs5e', 'n3on': 'cmwcu6hns008x01lm6udwhqus'}
HUB = 'https://post-hub-nine.vercel.app'; KEY = open(os.path.expanduser('~/.posthub_key')).read().strip()
WORK = os.path.join(HERE, 'work', 'stream'); os.makedirs(WORK, exist_ok=True)
USED = os.path.join(HERE, 'data', 'stream_used.txt')   # saved back to the repo after cloud runs, so Mac + cloud never reuse a clip
used = set(open(USED).read().split()) if os.path.exists(USED) else set()
BIN = os.path.expanduser('~/.local/bin')
MIN_POOL, MIN_OWN = 150, 40          # minimum clip views: other streamers' clips must be proven; a page's own streamer just can't be dead
AUTO = {'vicecityrp'}   # pages that post without approval (owner only reviews GTA 6 pages)
MAIN = {'kai': 'kaicenat', 'adin': 'adinross', 'n3on': 'n3on'}   # fan pages: their own streamer


def hub(path, body=None):
    req = urllib.request.Request(HUB + path, data=json.dumps(body).encode() if body else None, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY, 'Origin': HUB})
    return json.load(urllib.request.urlopen(req, timeout=240))


def owner_feedback(page):
    """Why the owner rejected recent clips (Clip Studio reasons) — the AI must avoid repeating these."""
    try: fb = hub('/api/studio?feedback=1').get('feedback', [])
    except Exception: return ''
    rows = [f"- {x['reason']} (\"{x.get('caption', '')[:60]}\")" for x in fb[-25:] if x.get('page') in (page, None) or True]
    return ('\nThe owner REJECTED these recent clips — do not pick clips with the same problems:\n' + '\n'.join(rows[-15:])) if rows else ''


def burned_captions(mp4, s0, e0):
    """Does the source already have subtitles/captions burned in? (AI looks at a small preview of the moment)"""
    from gemini import ask_json_video
    prev = mp4 + '.prev.mp4'
    subprocess.run([os.path.join(BIN, 'ffmpeg'), '-y', '-loglevel', 'error', '-ss', f'{s0:.1f}', '-t', f'{min(8, e0 - s0):.1f}', '-i', mp4, '-vf', 'scale=480:-2', '-r', '6', '-an', '-c:v', 'libx264', '-crf', '32', prev])
    try: return bool(ask_json_video(prev, 'Does this video ALREADY have subtitles or captions burned into the picture (text lines of what people are saying, in any language)? Ignore game HUD, menus and chat boxes. Return JSON {"captions": true/false}').get('captions'))
    except Exception: return False
    finally:
        if os.path.exists(prev): os.remove(prev)


def inspect(out, job, j, need6):
    """Quality inspector (same rules as the morning batch): watches the finished clip, drops weak/unoriginal ones, applies its trim + hook fixes."""
    from review import review
    try: rv = review(out, job['hook'], j['caption'], need6)
    except Exception as e: print('  inspector unavailable:', str(e)[:60], flush=True); return True, ''
    ov = int(rv.get('overall') or 0); orig = int((rv.get('scores') or {}).get('originality') or 100)
    print(f"  inspector: {ov}/100 {rv.get('verdict')} | {'; '.join(rv.get('issues', [])[:2])[:120]}", flush=True)
    if need6 and rv.get('is_gta6') is False and ov < 60: return False, 'not GTA 6'
    if rv.get('watermark') or orig < 35: return False, f'unoriginal risk ({orig})'
    if rv.get('regulated') or rv.get('mature'): return False, f"For You risk: {rv.get('risk_reason') or 'regulated/mature'}"   # Nov 19: 5 Physix videos restricted for Regulated Goods
    if rv.get('verdict') == 'skip' and ov < 40: return False, f'weak ({ov})'
    fx = rv.get('fixes') or {}; ts, te = float(fx.get('trim_start') or 0), float(fx.get('trim_end') or 0); hk = (fx.get('hook') or '').strip()
    if ts >= 0.4 or te >= 0.4 or (hk and hk != job['hook'] and len(hk) <= 60):
        j2 = dict(job, start=job['start'] + min(ts, 6), end=job['end'] - min(te, 8), hook=hk or job['hook'])
        if j2['end'] - j2['start'] >= 8:
            try: render(j2); j['hook'] = j2['hook']; print('  inspector fixes applied (trim/hook)', flush=True)
            except Exception as e: print('  fix failed, keeping original cut', str(e)[:60], flush=True)
    return True, ''


MOMENTS = os.path.join(HERE, 'data', 'moments.json')   # what was SAID in every clip made (shared with the daily run, saved to the repo)
def _mw(words, s0, e0):
    import re
    return {re.sub(r'[^a-z0-9]', '', w['w'].lower()) for w in words if w['e'] > s0 and w['s'] < e0 and len(re.sub(r'[^a-z0-9]', '', w['w'].lower())) >= 3}
def seen_moment(words, s0, e0):
    """Same moment clipped by a different viewer (new link, new caption)? Checked across ALL pages: GTA 6 pages share streamers."""
    a = _mw(words, s0, e0)
    try: m = json.load(open(MOMENTS))
    except Exception: m = {}
    for pg, v in m.items():
        for x in v:
            b = set(x.get('w') or [])
            if len(a) >= 6 and len(b) >= 6 and len(a & b) / min(len(a), len(b)) >= 0.6: return pg
    return None
def remember_moment(page, words, s0, e0):
    import datetime
    try: m = json.load(open(MOMENTS))
    except Exception: m = {}
    m.setdefault(page, []).append({'w': sorted(_mw(words, s0, e0)), 'd': datetime.date.today().isoformat()})
    json.dump(m, open(MOMENTS, 'w'))


def brain(page):
    b = os.path.join(HERE, 'brain'); return open(os.path.join(b, '_shared.md')).read() + '\n' + open(os.path.join(b, page + '.md')).read()


def candidates(d):
    out = []; plat_of = {}
    for plat, ch, want, flt in F['PAGES'][d]:
        try:
            got = F['kick_list'](ch, flt) if plat == 'kick' else F['kick_cat_list'](ch) if plat == 'kickcat' else F['twitch_cat_list'](only=ch, hours=96) if plat == 'twitchcat' and ch.islower() else F['twitch_cat_list'](ch) if plat == 'twitchcat' else F['twitch_list'](ch)
            for x in got: plat_of[x['url']] = plat; x.setdefault('streamer', ch)
            out += got
        except Exception as e: print('  list failed', plat, ch, str(e)[:80], flush=True)
    seen = set(); res = []
    for c in sorted(out, key=lambda c: (not (c.get('kick') or c.get('gta6')), -c['views'])):   # game-labeled clips first (Kick + Twitch GTA VI category), then unlabeled Twitch
        if c['url'] in seen or c['url'] in used or (c.get('dur') and c['dur'] > 90): continue
        pooled = plat_of.get(c['url']) in ('kickcat', 'twitchcat') or c.get('streamer') not in (None, '', MAIN.get(d))
        if c['views'] < (MIN_POOL if pooled else MIN_OWN): continue
        if d not in MAIN and c.get('streamer') in MAIN.values(): continue   # Kai/Adin/N3on clips are saved for their own fan pages      # proven moments only: viewers already watched it
        seen.add(c['url']); res.append(c)
    return res


print('loading speech model…', flush=True)
model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=os.cpu_count() or 4)
queues = {d: None for d in ORDER}; made = {d: 0 for d in ORDER}; tries = {d: 0 for d in ORDER}
try:   # count clips already waiting in Clip Studio (so a restart doesn't overshoot)
    for x in hub('/api/studio').get('drafts', []):
        d = next((k for k in ORDER if PAGEKEY.get(k, k) == x.get('page')), None)
        if d: made[d] += 1
    acct = {'vicecityrp': 'vicecityrpnet'}       # auto pages: count clips already scheduled ahead, so the queue doesn't pile up
    for x in hub('/api/posts?all=1').get('posts', []):
        pl = (x.get('platforms') or [{}])[0]
        for d, name in acct.items():
            if d in made and x.get('status') == 'SCHEDULED' and pl.get('accountName') == name: made[d] += 1
    print('already in Clip Studio / scheduled:', made, flush=True)
except Exception: pass
t_start = time.time()
while any(made[d] < TARGET and tries[d] < (40 if d == 'physix' else 25) for d in ORDER) and time.time() < STOP_AT:
    for d in ORDER:
        if made[d] >= TARGET or tries[d] >= (40 if d == 'physix' else 25) or time.time() >= STOP_AT: continue
        page = PAGEKEY.get(d, d)
        if queues[d] is None: queues[d] = candidates(d); print(f'{page}: {len(queues[d])} candidate clips', flush=True)
        if not queues[d]: tries[d] = 99; continue
        c = queues[d].pop(0); tries[d] += 1; used.add(c['url']); open(USED, 'a').write(c['url'] + '\n')
        n = f'{d}_{int(time.time())}'; mp4 = os.path.join(WORK, n + '.mp4')
        cmd = [os.path.join(BIN, 'yt-dlp'), '-q', '--no-warnings', '--ffmpeg-location', BIN, '-f', 'best[height<=1080]/best', '-o', mp4]
        if c.get('kick'): cmd += ['--hls-prefer-native', '--add-header', f"User-Agent:{F['UA']}"]
        try:
            if subprocess.run(cmd + [c['url']], timeout=200).returncode or not os.path.exists(mp4): continue
            segs, _ = model.transcribe(mp4, word_timestamps=True, vad_filter=True, language='en'); segs = list(segs)
        except Exception as e: print('  skip', str(e)[:60], flush=True); continue
        words = [{'w': w.word.strip(), 's': round(w.start, 2), 'e': round(w.end, 2)} for s in segs for w in (s.words or [])]
        if len(words) < 8: print(f'  {page}: skip (no talking)', flush=True); continue
        wp = os.path.join(WORK, n + '.words.json'); json.dump(words, open(wp, 'w'))
        tr = '\n'.join(f'[{s.start:.1f}-{s.end:.1f}] {s.text.strip()}' for s in segs)[:5000]
        try:
            j = ask_json(f"""You run a TikTok clip page. Page rules:\n{brain(page)}\n
{owner_feedback(page)}
Judge ONE raw clip (streamer: {c.get('streamer') or c.get('title','')}, title: {c.get('title','')!r}, {c['views']} views). The owner reviews every clip, so say yes to decent ones; say no only if it breaks a hard rule or truly nothing happens.{' GTA 6 LAUNCH WEEK: on this page ANY funny, hype or wild GTA 6 gameplay moment counts (chases, crashes, fails, NPC chaos, first reactions to the game) — it does NOT have to be a physics fail.' if page == 'gta6physix' else ''}
Return JSON {{"use": true/false, "why": "short", "start": seconds, "end": seconds (12-45s long, start right before the moment), "hook": "max 55 chars, no emoji, true", "caption": "1 punchy line + emoji\\nFollow line\\n4-5 hashtags incl #gta6 #gtavi (Vice City RP page: #gtarp #nopixel instead; N3on page: #n3on #kick, plus #gta6 only if it is GTA 6)"}}
Transcript:\n{tr}""")
        except Exception as e: print('  AI failed', str(e)[:60], flush=True); continue
        if not j.get('use'): print(f"  {page}: no — {j.get('why','')[:70]}", flush=True); continue
        s0, e0 = max(0.0, float(j['start'])), float(j['end'])
        if not 8 <= e0 - s0 <= 50: s0, e0 = 0.0, min(45.0, words[-1]['e'] + 0.5)
        dup = seen_moment(words, s0, e0)
        if dup: print(f'  {page}: skip — same moment already made for {dup}', flush=True); continue
        out = os.path.join(WORK, n + '_final.mp4')
        try:
            burned = burned_captions(mp4, s0, e0)
            if burned: print(f'  {page}: source already has subtitles -> hook + mascot only (no extra captions)', flush=True)
            job = {'src': mp4, 'words': '' if burned else wp, 'mwords': wp, 'start': s0, 'end': e0, 'hook': j['hook'], 'out': out, 'layout': 'full', 'cx': 0.5, 'mascot': page}
            render(job)
            ok, why = inspect(out, job, j, need6=page not in ('vicecityrp', 'n3on') and not c.get('kick') and not c.get('gta6'))   # the AI watches the finished clip
            if not ok: print(f'  {page}: inspector dropped it — {why}', flush=True); continue
            u = hub('/api/upload', {'files': [{'fileName': n + '.mp4', 'mimeType': 'video/mp4'}]})['urls'][0]
            code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--retry', '3', '-X', 'PUT', '-H', 'Content-Type: video/mp4', '--data-binary', '@' + out, u['uploadUrl']], capture_output=True, text=True).stdout
            if not code.startswith('2'): print('  upload failed', code, flush=True); continue
            r = hub('/api/post', {'accountIds': [ACCT[page]], 'contentType': 'VIDEO', 'text': j['caption'], 'mediaUrls': [u['publicUrl']], 'draft': True})['results'][0]
            if r.get('ok') and page in AUTO:    # straight to the next open slot (TikTok + YouTube)
                try:
                    dft = next(x for x in hub('/api/studio').get('drafts', []) if x.get('page') == page and u['publicUrl'].split('/')[-1] in (x.get('media') or ''))
                    a = hub('/api/studio', {'action': 'approve', 'postId': dft['id']}); print(f"  {page}: auto-approved -> {a.get('scheduledAt')}", flush=True)
                except Exception as e: print('  auto-approve failed (left in Studio)', str(e)[:60], flush=True)
            if r.get('ok'): remember_moment(page, words, s0, e0)
            if r.get('ok'): made[d] += 1; print(f"✅ {page} #{made[d]} in Clip Studio ({(time.time() - t_start) / 60:.0f} min): {j['hook']}", flush=True)
            else: print('  draft failed', r.get('problems'), flush=True)
        except Exception as e: print('  cut/upload failed', str(e)[:80], flush=True)
        finally:
            for f in (mp4,): 
                if os.path.exists(f): os.remove(f)
print('DONE', made, f'{(time.time() - t_start) / 60:.0f} min', flush=True)
try: hub('/api/push', {'action': 'send', 'title': 'Clip Studio 🎬', 'body': f'{sum(made.values())} GTA 6 clips ready to approve', 'url': '/#studio'})
except Exception: pass

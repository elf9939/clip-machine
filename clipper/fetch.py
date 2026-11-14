#!/usr/bin/env python3
"""Daily batch fetcher: top viewer-made clips per page -> download (gap-checked) -> transcribe.
   .venv/bin/python fetch.py <batch_name>
   Writes work/<batch>/<page>/NN.mp4 + NN.words.json + index.txt (title, views, transcript with times)
   for Claude to pick trims/hooks, then split.py renders.
"""
import json, os, re, subprocess, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clip import YTDLP, FFMPEG, BIN, ROOT

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
GTA = lambda c: 'grand theft auto' in (c.get('category') or {}).get('name', '').lower()
NOT_GTA = lambda c: not GTA(c)

# page -> list of (platform, channel, how many, filter)
PAGES = {
    'kai':        [('twitch', 'kaicenat', 10, None)],
    'adin':       [('kick', 'adinross', 9, None)],
    'n3on':       [('kick', 'n3on', 9, None)],
    'pulsevice':  [('kick', 'xqc', 4, NOT_GTA), ('twitch', 'jynxzi', 5, None), ('twitch', 'lacy', 5, None),
                   ('twitch', 'caseoh_', 4, None), ('twitch', 'stableronaldo', 4, None), ('kick', 'sneako', 2, None)],
    'vicecityrp': [('kick', 'buddha', 6, GTA), ('kick', 'dasmehdi', 3, GTA), ('kick', 'ramee', 3, GTA)],
    'physix':     [('kick', 'xqc', 6, GTA), ('kick', 'buddha', 3, GTA), ('kick', 'dasmehdi', 3, GTA), ('kick', 'ramee', 3, GTA)],
}

used_file = os.path.join(ROOT, 'work', 'used_clips.txt')
used = set(open(used_file).read().split()) if os.path.exists(used_file) else set()
for f in [os.path.join(ROOT, 'work', d, 'list.txt') for d in ('gta', 'kick')]:
    if os.path.exists(f): used |= {l.split()[1] for l in open(f) if len(l.split()) > 1}


def kick_list(ch, flt):
    out = []
    for span in ('day', 'week'):
        req = urllib.request.Request(f'https://kick.com/api/v2/channels/{ch}/clips?sort=view&time={span}', headers={'User-Agent': UA})
        try: data = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e: print('  kick list failed', ch, span, e, flush=True); continue
        for c in data.get('clips', []):
            if flt and not flt(c): continue
            if c['clip_url'] in used or any(c['clip_url'] == o['url'] for o in out): continue
            out.append({'url': c['clip_url'], 'title': c.get('title', ''), 'views': c.get('views', 0), 'kick': True,
                        'dur': c.get('duration', 0)})
    return out


def twitch_list(ch):
    out = []
    for rng in ('24hr', '7d'):
        r = subprocess.run([YTDLP, '--flat-playlist', '--playlist-end', '25', '--print', '%(url)s\t%(view_count)s\t%(title)s',
                            f'https://www.twitch.tv/{ch}/clips?filter=clips&range={rng}'], capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            u, v, t = (ln.split('\t') + ['', ''])[:3]
            if u in used or any(u == o['url'] for o in out): continue
            out.append({'url': u, 'title': t, 'views': int(v) if v.isdigit() else 0, 'kick': False, 'dur': 0})
        if len(out) >= 15: break
    return out


def gaps_ok(path):
    r = subprocess.run([FFMPEG, '-v', 'error', '-i', path, '-map', '0:v', '-f', 'framecrc', '-'], capture_output=True, text=True)
    pts = [int(l.split(',')[2]) for l in r.stdout.splitlines() if l and not l.startswith('#')]
    tb = re.search(r'#tb 0: (\d+)/(\d+)', r.stdout)
    if not pts or not tb: return False
    sec = int(tb.group(1)) / int(tb.group(2))
    return max((b - a) * sec for a, b in zip(pts, pts[1:])) < 0.2 if len(pts) > 1 else False


def main(batch):
    from faster_whisper import WhisperModel
    model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=4)
    for page, srcs in PAGES.items():
        d = os.path.join(ROOT, 'work', batch, page); os.makedirs(d, exist_ok=True)
        idx_path = os.path.join(d, 'index.txt'); n = len([f for f in os.listdir(d) if f.endswith('.words.json')])
        for plat, ch, want, flt in srcs:
            if os.environ.get('CLOUD') and page in ('kai', 'adin', 'n3on'): want = min(want, 3)   # warming pages: keep cloud minutes low
            cands = kick_list(ch, flt) if plat == 'kick' else twitch_list(ch)
            cands = sorted(cands, key=lambda c: -c['views'])
            print(f'{page}/{ch}: {len(cands)} new clips found, taking {want}', flush=True)
            got = 0
            for c in cands:
                if got >= want: break
                if c['dur'] and c['dur'] > 90: continue
                n += 1; mp4 = os.path.join(d, f'{n:02d}.mp4')
                cmd = ['nice', '-n', '10', YTDLP, '-q', '--ffmpeg-location', BIN, '-f', 'best[height<=1080]/best', '-o', mp4]
                if c['kick']: cmd[4:4] = ['--hls-prefer-native', '--add-header', f'User-Agent:{UA}']
                subprocess.run(cmd + [c['url']])
                with open(used_file, 'a') as f: f.write(c['url'] + '\n')
                if not os.path.exists(mp4) or not gaps_ok(mp4):
                    print('  skip (download failed or skips frames):', c['title'], flush=True)
                    if os.path.exists(mp4): os.remove(mp4)
                    n -= 1; continue
                segs, info = model.transcribe(mp4, word_timestamps=True, vad_filter=True, language='en')
                segs = list(segs)
                words = [{'w': w.word.strip(), 's': round(w.start, 2), 'e': round(w.end, 2)} for s in segs for w in (s.words or [])]
                json.dump(words, open(os.path.join(d, f'{n:02d}.words.json'), 'w'))
                lines = '\n'.join(f'   [{s.start:5.1f}-{s.end:5.1f}] {s.text.strip()}' for s in segs)
                with open(idx_path, 'a') as f:
                    f.write(f'\n## {n:02d} | {ch} | {c["views"]} views | {info.duration:.0f}s | {c["title"]}\n{lines}\n')
                got += 1
                print(f'  ✓ {page} {n:02d} {c["title"][:50]} ({c["views"]} views)', flush=True)
    print('BATCH DONE', flush=True)


if __name__ == '__main__':
    main(sys.argv[1])

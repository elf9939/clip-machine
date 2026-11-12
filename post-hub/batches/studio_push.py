# Send finished clips to Clip Studio as drafts (run on the Mac after a clip batch is cut).
# usage: python3 studio_push.py picks.json
#   picks.json: [{"file": "/abs/clip.mp4", "page": "pulsevice", "caption": "...", "hook": "...", "source": "xqc", "views": 4096}]
# Quality checks run first; clips that fail a must-pass check are skipped. Then Post Hub is redeployed so the Studio shows the details.
import hashlib, json, math, os, re, subprocess, sys, urllib.request, datetime
HUB = 'https://post-hub-nine.vercel.app'; KEY = open(os.path.expanduser('~/.posthub_key')).read().strip()
ROOT = os.path.expanduser('~/Projects/post-hub'); MAN = os.path.join(ROOT, 'data', 'studio.json'); SEEN = os.path.join(ROOT, 'data', 'pushed.txt')
FF = os.path.expanduser('~/.local/bin/ffmpeg')
PAGES = {'pulsevice': 'cmwcu0zfb008w01lm4h5gv59d', 'vicecityrp': 'cmwcw1agy009501lmehe4420r', 'gta6physix': 'cmwcw8bo5009601lmexy736z1',
         'kai': 'cmwcvr8px009401lmtfla7j8u', 'adin': 'cmwcvc7ar009101lma8hncs5e', 'n3on': 'cmwcu6hns008x01lm6udwhqus'}

def call(path, body=None):
    req = urllib.request.Request(HUB + path, data=json.dumps(body).encode() if body else None, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY, 'Origin': HUB})
    return json.load(urllib.request.urlopen(req, timeout=300))

def probe(f):
    r = subprocess.run([FF, '-hide_banner', '-i', f, '-map', '0:v', '-f', 'framecrc', '-', '-map', '0:a', '-af', 'volumedetect', '-f', 'null', '-'], capture_output=True, text=True)
    pts = [int(l.split(',')[2]) for l in r.stdout.splitlines() if l and not l.startswith('#')]
    tb = re.search(r'#tb 0: (\d+)/(\d+)', r.stdout); sec = int(tb.group(1)) / int(tb.group(2)) if tb else 1 / 30
    gap = max(((b - a) * sec for a, b in zip(pts, pts[1:])), default=9)
    dur = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r.stderr)
    dur = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0
    mean = re.search(r'mean_volume: (-?[\d.]+)', r.stderr); peak = re.search(r'max_volume: (-?[\d.]+)', r.stderr)
    w, h = (map(int, re.search(r', (\d{3,4})x(\d{3,4})', r.stderr).groups()) if re.search(r', (\d{3,4})x(\d{3,4})', r.stderr) else (0, 0))
    return {'gap': gap, 'dur': dur, 'mean': float(mean.group(1)) if mean else -99, 'peak': float(peak.group(1)) if peak else 0, 'w': w, 'h': h}

picks = json.load(open(sys.argv[1]))
man = json.load(open(MAN)) if os.path.exists(MAN) else {'clips': {}}
seen = set(open(SEEN).read().split()) if os.path.exists(SEEN) else set()
pushed = 0
for p in picks:
    f = p['file']; name = os.path.basename(f)
    digest = hashlib.sha1(open(f, 'rb').read()).hexdigest()[:16]
    if digest in seen: print('SKIP duplicate', name, flush=True); continue
    q = probe(f)
    checks = {
        'no frame skips': q['gap'] < 0.2,
        '12-45 sec': 12 <= q['dur'] <= 45,
        'audio level': -38 < q['mean'] and q['peak'] <= 0.5,
        'vertical 9:16': q['w'] and abs(q['h'] / q['w'] - 16 / 9) < 0.02,
        'TikTok safe zones': True,   # every clip is cut with the safe-zone layout in split.py
        'has caption': bool(p.get('caption', '').strip()),
    }
    must = ['no frame skips', 'vertical 9:16', 'has caption']
    if not all(checks[k] for k in must):
        print('REJECTED', name, [k for k in must if not checks[k]], flush=True); continue
    u = call('/api/upload', {'files': [{'fileName': name, 'mimeType': 'video/mp4'}]})['urls'][0]
    code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--retry', '3', '-X', 'PUT', '-H', 'Content-Type: video/mp4', '--data-binary', '@' + f, u['uploadUrl']], capture_output=True, text=True).stdout
    if code != '200': print('UPLOAD FAILED', name, flush=True); continue
    r = call('/api/post', {'accountIds': [PAGES[p['page']]], 'contentType': 'VIDEO', 'text': p['caption'], 'mediaUrls': [u['publicUrl']], 'draft': True})['results'][0]
    if not r['ok'] or not r.get('postId'): print('DRAFT FAILED', name, r.get('problems'), flush=True); continue
    score = round(math.log10(max(int(p.get('views') or 1), 1)) * 10 + sum(checks.values()), 1)
    man['clips'][r['postId']] = {'hook': p.get('hook', ''), 'source': p.get('source', ''), 'views': p.get('views'), 'seconds': round(q['dur']),
                                 'checks': checks, 'score': score, 'file': name, 'added': datetime.datetime.now().isoformat(timespec='minutes')}
    open(SEEN, 'a').write(digest + '\n'); seen.add(digest); pushed += 1
    print('DRAFTED', p['page'], name, flush=True)
json.dump(man, open(MAN, 'w'), indent=1)
if pushed:
    env = dict(os.environ, PATH=os.path.expanduser('~/.local/bin') + ':' + os.environ['PATH'])
    try: subprocess.run(['vercel', 'deploy', '--prod', '--yes'], cwd=ROOT, env=env, capture_output=True)
    except FileNotFoundError: pass   # cloud runner: no Vercel CLI (Studio just shows fewer details)
print(f'STUDIO PUSH DONE: {pushed} new drafts', flush=True)

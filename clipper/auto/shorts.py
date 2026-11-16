#!/usr/bin/env python3
"""Winners → YouTube Shorts. Runs every 4h (views workflow).
   Takes clip-page TikToks posted 24h+ ago, ranks them by TikTok views, and schedules the best unposted ones
   to that page's YouTube channel — max 2 per channel per day, at each channel's own times."""
import datetime, json, os, subprocess, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); DONE = os.path.join(os.path.dirname(HERE), 'data', 'shorts_done.txt')
HUB = 'https://post-hub-nine.vercel.app'; KEY = open(os.path.expanduser('~/.posthub_key')).read().strip()
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY, 'Origin': HUB}
YTDLP = os.path.expanduser('~/.local/bin/yt-dlp')
# TikTok username -> (YouTube account id, YouTube posting times Central)
PAIR = {'pulseviceclips': ('cmwgl7csz001101nz9e8ubsa9', ['11:00', '17:00']), 'vicecityrpnet': ('cmwgl927y001301nzullmbptl', ['12:00', '18:00']),
        'gta6physixhub': ('cmwgl9tf5001401nzr9lymymm', ['13:00', '19:00']), 'kai_clips_daily_': ('cmwgl85pu001201nzaddswju1', ['11:30', '17:30']),
        'adin_clips_daily': ('cmwgl5a0w000y01nzzo0wk7c7', ['12:30', '18:30']), 'neonpulseclips0': ('cmwgl6a8u000z01nznkxuhsqg', ['13:30', '19:30'])}
CT = datetime.timedelta(hours=-6)

def call(path, body=None):
    return json.load(urllib.request.urlopen(urllib.request.Request(HUB + path, data=json.dumps(body).encode() if body else None, headers=H), timeout=240))

def tiktok_views(user):
    r = subprocess.run([YTDLP, '--socket-timeout', '30', '--print', '%(view_count)s\t%(title)s', f'https://www.tiktok.com/@{user}'], capture_output=True, text=True, timeout=240)
    out = {}
    for ln in r.stdout.splitlines():
        v, t = (ln.split('\t') + [''])[:2]
        if v.isdigit(): out[t.strip()[:40].lower()] = int(v)
    return out

done = set(open(DONE).read().split()) if os.path.exists(DONE) else set()
posts = call('/api/posts?all=1')['posts']
now = datetime.datetime.now(datetime.timezone.utc)
made = []
for user, (yt, times) in PAIR.items():
    pub = [p for p in posts if p['status'] == 'COMPLETED' and (p.get('platforms') or [{}])[0].get('accountName') == user and p['id'] not in done
           and p.get('mediaUrls') and (p['platforms'][0].get('publishedAt') or '') and
           now - datetime.datetime.fromisoformat(p['platforms'][0]['publishedAt'].replace('Z', '+00:00')) > datetime.timedelta(hours=24)]
    if not pub: continue
    vmap = tiktok_views(user)
    for p in pub: p['_views'] = vmap.get((p.get('text') or '').strip()[:40].lower(), 0)
    pub.sort(key=lambda p: -p['_views'])
    taken = {p['scheduledAt'][:16] for p in posts if p['status'] == 'SCHEDULED' and (p.get('platforms') or [{}])[0].get('connectionId') == yt}
    # fill this channel's open slots for the next 2 days (2 per day max), best clips first
    slots = []
    for day in range(0, 3):
        d = (now + CT).date() + datetime.timedelta(days=day)
        for t in times:
            hh, mm = map(int, t.split(':')); utc = datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=datetime.timezone.utc) - CT
            if utc > now + datetime.timedelta(minutes=20) and utc.strftime('%Y-%m-%dT%H:%M') not in taken: slots.append(utc)
    for p, slot in zip(pub, slots[:4]):
        r = call('/api/post', {'accountIds': [yt], 'contentType': 'VIDEO', 'text': p['text'], 'mediaUrls': p['mediaUrls'][:1], 'scheduledAt': slot.strftime('%Y-%m-%dT%H:%M:00Z')})['results'][0]
        if r['ok']:
            done.add(p['id']); made.append((user, p['_views'], (slot + CT).strftime('%a %I:%M%p'), p['text'][:40]))
open(DONE, 'w').write('\n'.join(sorted(done)) + '\n')
for m in made: print('SHORT', *m)
print('SHORTS DONE', len(made))

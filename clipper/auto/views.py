#!/usr/bin/env python3
"""Quick view check (runs every 4h on GitHub): TikTok views per account -> PostBotz dashboard chart + Analytics robot.
   No notification. If an account fails to load, its last good number is kept so totals never fake-drop."""
import datetime, json, os, subprocess, urllib.request
HUB = 'https://post-hub-nine.vercel.app'; KEY = open(os.path.expanduser('~/.posthub_key')).read().strip()
YTDLP = os.path.expanduser('~/.local/bin/yt-dlp')
ACCTS = {'pulseviceclips': 'PulseVice', 'vicecityrpnet': 'ViceCityRP', 'gta6physixhub': 'GTA6Physix', 'kai_clips_daily_': 'Kai', 'adin_clips_daily': 'Adin',
         'neonpulseclips0': 'N3on', 'violet_crane': 'Violet', 'siennahart9': 'Sienna'}
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY, 'Origin': HUB}

def call(path, body=None):
    return json.load(urllib.request.urlopen(urllib.request.Request(HUB + path, data=json.dumps(body).encode() if body else None, headers=H), timeout=60))

def views(user):
    r = subprocess.run([YTDLP, '--socket-timeout', '30', '--retries', '3', '--print', '%(view_count)s', f'https://www.tiktok.com/@{user}'], capture_output=True, text=True, timeout=300)
    vals = [int(x) for x in r.stdout.split() if x.isdigit()]
    return sum(vals), len(vals)

hist = call('/api/agents').get('stats', [])
last = hist[-1]['accounts'] if hist else {}
today = (datetime.datetime.utcnow() - datetime.timedelta(hours=6)).date().isoformat()   # Central date
prev_day = next((h for h in reversed(hist) if h['date'] < today), None)
accounts, notes = {}, []
for user, name in ACCTS.items():
    try: v, n = views(user)
    except Exception: v, n = 0, 0
    if n == 0 and last.get(name): v = last[name]; notes.append(f'{name} kept last value')
    if v or name in last: accounts[name] = v
# YouTube Shorts: views per channel from AdaptlyPost analytics (official YouTube API; scraping YouTube is blocked from the cloud)
YT_NAMES = {'PulseVice': 'PulseVice', 'Vice City RP': 'ViceCityRP', 'GTA6 Physix': 'GTA6Physix', 'Kai Clips Daily': 'Kai', 'Adin Clips Daily': 'Adin', 'N3on Clips': 'N3on'}
try:
    try: call('/api/accounts?analytics=1&sync=1')          # ask for fresh numbers for next time
    except Exception: pass
    yt = {}
    for p in call('/api/accounts?analytics=1&platforms=YOUTUBE&days=90')['posts']:
        key = YT_NAMES.get(p.get('accountName'), p.get('accountName')) + ' YT'
        yt[key] = yt.get(key, 0) + int((p.get('metrics') or {}).get('views') or 0)
    for key, v in yt.items():
        if v == 0 and last.get(key): v = last[key]; notes.append(key + ' kept last value')
        accounts[key] = v
except Exception as e:
    notes.append(f'YouTube check failed: {e}')
total = sum(accounts.values())
call('/api/push', {'action': 'stats', 'date': today, 'total': total, 'accounts': accounts})
gain = f" (+{total - prev_day['total']:,} today)" if prev_day else ''
call('/api/push', {'action': 'status', 'agent': 'analytics', 'state': 'done', 'summary': f'{total:,} total views (TikTok + YouTube){gain} · checked {datetime.datetime.utcnow() - datetime.timedelta(hours=6):%I:%M %p}'})
print(today, total, accounts, notes)

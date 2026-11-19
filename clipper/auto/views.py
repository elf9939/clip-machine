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
    return json.load(urllib.request.urlopen(urllib.request.Request(HUB + path, data=json.dumps(body).encode() if body else None, headers=H), timeout=240))

PUBLIC = {}   # account -> {video id: views} as the public sees it
def views(user):
    r = subprocess.run([YTDLP, '--socket-timeout', '30', '--retries', '3', '--print', '%(id)s %(view_count)s', f'https://www.tiktok.com/@{user}'], capture_output=True, text=True, timeout=300)
    got = {a: int(b) for a, b in (l.split() for l in r.stdout.splitlines() if len(l.split()) == 2 and l.split()[1].isdigit())}
    PUBLIC[user] = got
    return sum(got.values()), len(got)


def stuck_alarm():
    """NO-VIEWS ALARM (Nov 19: 7 Adin posts sat at 0 views for a day before anyone noticed).
    A post published 3+ hours ago that the public can't see, or that still has 0 views, is 'stuck'.
    2+ stuck posts on a page -> phone alert right away, with which page and how many."""
    try: posts = call('/api/posts?all=1').get('posts', [])
    except Exception as e: return f'alarm skipped: {e}'
    now = datetime.datetime.utcnow(); stuck = {}
    for p in posts:
        for pl in p.get('platforms') or []:
            u = pl.get('accountName'); pid = pl.get('platformPostId'); at = pl.get('publishedAt')
            if pl.get('platform') != 'TIKTOK' or pl.get('status') != 'PUBLISHED' or u not in PUBLIC or not PUBLIC[u] or not pid or not at: continue
            age = (now - datetime.datetime.fromisoformat(at.replace('Z', ''))).total_seconds() / 3600
            if not 3 <= age <= 72: continue
            if PUBLIC[u].get(pid, 0) == 0: stuck.setdefault(u, []).append(p.get('text', '').split('\n')[0][:40])
    bad = {u: v for u, v in stuck.items() if len(v) >= 2}
    if bad:
        body = ' · '.join(f"{ACCTS.get(u, u)}: {len(v)} posts at 0 views / hidden" for u, v in bad.items())
        try: call('/api/push', {'action': 'send', 'title': '⚠️ Posts not getting views', 'body': body + ' — check them in TikTok', 'url': '/#accounts'})
        except Exception: pass
        return 'ALARM ' + body
    return 'no stuck posts'

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
notes.append(stuck_alarm())
total = sum(accounts.values())
call('/api/push', {'action': 'stats', 'date': today, 'total': total, 'accounts': accounts})
gain = f" (+{total - prev_day['total']:,} today)" if prev_day else ''
call('/api/push', {'action': 'status', 'agent': 'analytics', 'state': 'done', 'summary': f'{total:,} total views (TikTok + YouTube){gain} · checked {datetime.datetime.utcnow() - datetime.timedelta(hours=6):%I:%M %p}'})
print(today, total, accounts, notes)

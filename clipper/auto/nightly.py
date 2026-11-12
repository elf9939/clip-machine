#!/usr/bin/env python3
"""Jarvis nightly report: TikTok views per account, best posts, schedule runway, failures, Violet chats, Studio drafts -> text.
   Also writes what's working into each page's Brand Brain so tomorrow's picks learn from it.
"""
import datetime, json, os, re, subprocess, sys, traceback, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from notify import send
HUB = 'https://post-hub-nine.vercel.app'; KEY = open(os.path.expanduser('~/.posthub_key')).read().strip()
YTDLP = os.path.expanduser('~/.local/bin/yt-dlp')
TT = {'pulseviceclips': ('PulseVice', 'pulsevice', 'cmwcu0zfb008w01lm4h5gv59d'), 'vicecityrpnet': ('ViceCityRP', 'vicecityrp', 'cmwcw1agy009501lmehe4420r'),
      'gta6physixhub': ('GTA6Physix', 'gta6physix', 'cmwcw8bo5009601lmexy736z1'), 'kai_clips_daily_': ('Kai', 'kai', 'cmwcvr8px009401lmtfla7j8u'),
      'adin_clips_daily': ('Adin', 'adin', 'cmwcvc7ar009101lma8hncs5e'), 'neonpulseclips0': ('N3on', 'n3on', 'cmwcu6hns008x01lm6udwhqus'),
      'violet_crane': ('Violet', None, 'cmwcte4cb008s01lm82j1ov5u'), 'siennahart9': ('Sienna', None, 'cmwctjf2n008v01lm25sjcuqb')}
STATS = os.path.join(HERE, 'stats'); os.makedirs(STATS, exist_ok=True)

def hub(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(HUB + path, headers={'Authorization': 'Bearer ' + KEY}), timeout=120))

def posts(status):
    out, off = [], 0
    while True:
        d = hub(f'/api/posts?status={status}&offset={off}'); out += d.get('posts', []); off += 100
        if not d.get('hasMore'): return out

def tiktok(user):
    r = subprocess.run(['nice', YTDLP, '--socket-timeout', '30', '--print', '%(timestamp)s\t%(view_count)s\t%(like_count)s\t%(title).60s',
                        f'https://www.tiktok.com/@{user}'], capture_output=True, text=True, timeout=600)
    vids = []
    for ln in r.stdout.splitlines():
        t, v, l, title = (ln.split('\t') + ['', '', '', ''])[:4]
        if t.isdigit(): vids.append({'t': int(t), 'views': int(v) if v.isdigit() else 0, 'likes': int(l) if l.isdigit() else 0, 'title': title})
    return vids

def learn(page, vids):
    if not page or not vids: return
    week = [v for v in vids if v['t'] > datetime.datetime.now().timestamp() - 7 * 86400] or vids
    best = sorted(week, key=lambda v: -v['views'])[:3]
    path = os.path.join(ROOT, 'brain', page + '.md'); txt = open(path).read().split('\n## What is working')[0].rstrip()
    lines = '\n'.join(f'- {v["views"]} views: "{v["title"]}"' for v in best)
    open(path, 'w').write(txt + f'\n\n## What is working (auto-updated {datetime.date.today()})\nTop posts this week — make more like these:\n{lines}\n')

def main():
    today = datetime.date.today().isoformat(); prev = {}
    pf = sorted(f for f in os.listdir(STATS) if f.endswith('.json') and f[:10] < today)
    if pf: prev = json.load(open(os.path.join(STATS, pf[-1])))
    now, lines, problems = {}, [], []
    for user, (name, page, conn) in TT.items():
        try: vids = tiktok(user)
        except Exception: vids = []
        total = sum(v['views'] for v in vids); now[user] = {'views': total, 'videos': len(vids)}
        gain = total - prev.get(user, {}).get('views', total)
        if vids: lines.append(f"• {name}: {total:,} views ({'+' if gain >= 0 else ''}{gain:,} today), {len(vids)} posts")
        learn(page, vids)
        if vids:
            top = max(vids, key=lambda v: v['views']); now[user]['top'] = top
    json.dump(now, open(os.path.join(STATS, today + '.json'), 'w'), indent=1)
    sched = posts('SCHEDULED'); runway = []
    for user, (name, page, conn) in TT.items():
        ts = sorted(p['scheduledAt'] for p in sched if (p.get('platforms') or [{}])[0].get('connectionId') == conn)
        if page in ('kai', 'adin', 'n3on'): continue          # still warming, posts by approval only
        last = ts[-1][:10] if ts else None
        days = (datetime.date.fromisoformat(last) - datetime.date.today()).days if last else -1
        if days <= 2: runway.append(f"{name} {'has NOTHING scheduled' if not last else 'runs out ' + last}")
    failed = [p for p in posts('FAILED') + posts('PARTIAL_FAILURE') if (p.get('updatedAt') or p.get('scheduledAt') or '')[:10] >= (datetime.date.today() - datetime.timedelta(days=1)).isoformat()]
    try: drafts = len(hub('/api/studio').get('drafts', []))
    except Exception: drafts = '?'
    chats = ''
    try:
        r = subprocess.run(['python3', os.path.expanduser('~/Projects/ai-influencers/violet-links/report.py')], capture_output=True, text=True, timeout=120)
        chats = r.stdout.strip().split('|')[-1].strip()
    except Exception: pass
    grand = sum(v['views'] for v in now.values()); ggain = grand - sum(v.get('views', 0) for v in prev.values()) if prev else 0
    msg = [f"🌙 Nightly report — {grand:,} total TikTok views" + (f" (+{ggain:,} today)" if prev else '')] + lines
    best = max((v for v in now.values() if v.get('top')), key=lambda v: v['top']['views'], default=None)
    if best: msg.append(f"🏆 Best post: \"{best['top']['title'][:45]}\" — {best['top']['views']:,} views")
    if chats: msg.append(f"💬 Violet's site (7 days): {chats}")
    msg.append(f"🎬 Clip Studio drafts waiting: {drafts}")
    if runway: problems.append('Schedule running low: ' + ', '.join(runway))
    if failed: problems.append(f'{len(failed)} post(s) failed in the last day — check Post Hub')
    msg += ['⚠️ ' + p for p in problems] or ['✅ No problems']
    send('\n'.join(msg))

if __name__ == '__main__':
    try: main()
    except Exception:
        send('⚠️ Jarvis nightly report crashed: ' + traceback.format_exc()[-300:]); raise

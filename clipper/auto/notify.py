# Jarvis notifications: iMessage to the user's iPhone via the Mac's Messages app.
# Config: ~/.jarvis.json {"imessage_to": "+13195551234"}  (phone number or Apple ID email)
# Falls back to a Mac notification + log if no number is set or Messages fails.
import json, os, shutil, subprocess, sys, datetime
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.log')
SCRIPT = ['on run argv', 'tell application "Messages"', 'set s to 1st account whose service type = iMessage',
          'send (item 2 of argv) to participant (item 1 of argv) of s', 'end tell', 'end run']

def push(text):
    """Post Hub app notification (the main channel). Nightly reports are also saved as the 7am brief."""
    import urllib.request
    hub = 'https://post-hub-nine.vercel.app'; key = open(os.path.expanduser('~/.posthub_key')).read().strip()
    hdr = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key, 'Origin': hub}
    title, _, body = text.partition('\n')
    try:
        if title.startswith('🌙'):
            urllib.request.urlopen(urllib.request.Request(hub + '/api/push', data=json.dumps({'action': 'brief', 'text': text}).encode(), headers=hdr), timeout=60)
        r = json.load(urllib.request.urlopen(urllib.request.Request(hub + '/api/push', data=json.dumps(
            {'action': 'send', 'title': title[:80], 'body': body[:1000], 'url': '/#studio' if 'draft' in text else '/'}).encode(), headers=hdr), timeout=60))
        return r.get('sent', 0) > 0
    except Exception as e:
        with open(LOG, 'a') as f: f.write(f'(push failed: {e})\n')
        return False

def send(text):
    with open(LOG, 'a') as f: f.write(f'\n[{datetime.datetime.now():%Y-%m-%d %H:%M}]\n{text}\n')
    if push(text): return True
    cfg = {}
    try: cfg = json.load(open(os.path.expanduser('~/.jarvis.json')))
    except Exception: pass
    to = cfg.get('imessage_to')
    if to and shutil.which('osascript'):
        r = subprocess.run(['osascript', *sum([['-e', l] for l in SCRIPT], []), to, text], capture_output=True, text=True)
        if r.returncode == 0: return True
        with open(LOG, 'a') as f: f.write(f'(iMessage failed: {r.stderr.strip()[:200]})\n')
    if not shutil.which('osascript'): return False   # cloud runner
    subprocess.run(['osascript', '-e', 'on run argv', '-e', 'display notification (item 1 of argv) with title "Jarvis"', '-e', 'end run', text[:200]])
    return False

if __name__ == '__main__':
    print('sent' if send(' '.join(sys.argv[1:]) or 'Jarvis test 🖤 texts are working.') else 'not sent by iMessage (see jarvis.log)')

def status(agent, state, summary=''):
    """Update a robot in Post Hub's Jarvis HQ. agent: research|writers|edit|qa|distribution|analytics|inbox|chief"""
    import urllib.request
    try:
        hub = 'https://post-hub-nine.vercel.app'; key = open(os.path.expanduser('~/.posthub_key')).read().strip()
        urllib.request.urlopen(urllib.request.Request(hub + '/api/push', data=json.dumps({'action': 'status', 'agent': agent, 'state': state, 'summary': summary}).encode(),
                               headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key, 'Origin': hub}), timeout=30)
    except Exception: pass

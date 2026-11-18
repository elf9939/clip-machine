#!/usr/bin/env python3
"""Animated page mascot for a finished clip.

The mascot sits small in the clearest corner for the WHOLE clip and changes pose every 2-4 seconds to match what's
happening (planned by the AI from the transcript), with a pop/bounce on every change and a big scale-up at the climax.

  apply(base_mp4, words, out_mp4, mascot_dir, seed)     # words = [{'w','s','e'}] with times relative to the clip start
"""
import json, math, os, random, subprocess, sys
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'auto'))
FFMPEG = os.path.expanduser('~/.local/bin/ffmpeg') if os.path.exists(os.path.expanduser('~/.local/bin/ffmpeg')) else 'ffmpeg'
W, H, FPS = 1080, 1920, 30
SIZE_H, MAX_W = 270, 200                       # ~18% of the frame width
CALM, POINT, TENSE = ['thinking', 'unimpressed', 'idle'], ['pointing'], ['shocked', 'cringe']
BIG = ['laughing', 'cryinglaugh', 'hype', 'facepalm', 'slowclap']
# corners inside the video area, clear of the hook (top), captions (centre ~y1170), TikTok's buttons (right side, lower half)
# and TikTok's caption/username block (bottom-left)
CORNERS = {'top-left': (28, 445), 'top-right': (W - 28 - MAX_W, 445), 'mid-left': (28, 1290)}


def duration(path):
    import re
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', subprocess.run([FFMPEG, '-i', path], capture_output=True, text=True).stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def pick_corner(base, dur):
    """Sample a few frames; choose the corner with the least detail/motion/skin (so we never cover faces or action)."""
    scores = {k: 0.0 for k in CORNERS}; prev = {}
    for k in range(6):
        t = dur * (0.1 + 0.15 * k)
        f = os.path.join('/tmp', f'mc_{os.getpid()}_{k}.png')
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', base, '-frames:v', '1', f])
        if not os.path.exists(f): continue
        im = Image.open(f).convert('RGB')
        for name, (x, y) in CORNERS.items():
            box = im.crop((x, y, x + MAX_W, y + SIZE_H))
            edges = sum(Image.Image.getdata(box.convert('L').filter(ImageFilter.FIND_EDGES))) / (MAX_W * SIZE_H)
            px = list(box.resize((20, 27)).getdata())
            skin = sum(1 for r, g, b in px if r > 95 and g > 40 and b > 20 and r > g and r > b and r - min(g, b) > 15) / len(px)
            motion = 0.0
            if name in prev:
                a, b2 = prev[name], box.convert('L').resize((40, 54))
                motion = sum(abs(p - q) for p, q in zip(a.getdata(), b2.getdata())) / (40 * 54)
            prev[name] = box.convert('L').resize((40, 54))
            scores[name] += edges + 60 * skin + 0.6 * motion
        os.remove(f)
    return min(scores, key=scores.get)


def plan(words, dur, have, seed):
    """AI plans the pose timeline from the transcript; falls back to a varied heuristic if the AI is unavailable."""
    rnd = random.Random(seed)
    lines, cur, t0 = [], [], 0.0
    for w in words:
        if not cur: t0 = w['s']
        cur.append(w['w'])
        if w['e'] - t0 > 2.5: lines.append(f'[{t0:.1f}s] ' + ' '.join(cur)); cur = []
    if cur: lines.append(f'[{t0:.1f}s] ' + ' '.join(cur))
    segs = None
    try:
        from gemini import ask_json
        segs = ask_json(f"""Plan the reaction poses of a small cartoon mascot watching this {dur:.1f}-second clip (it reacts like a viewer).
Available poses: {', '.join(sorted(have))}.
Rules: cover 0 to {dur:.1f}s with back-to-back segments of 2-4 seconds each. Never use the same pose twice in a row or repeat a sequence. Vary the order.
- calm / setup moments: thinking, unimpressed{', idle' if 'idle' in have else ''}
- something interesting about to happen: pointing
- build-up / tension: shocked or cringe
- big reactions (laughing, cryinglaugh, hype, facepalm, slowclap) are ONLY allowed in the climax segment
- after the climax, settle into a calm pose that fits (thinking or unimpressed)
- exactly ONE climax segment (1-1.6s) at the funniest/biggest moment with a big reaction that MATCHES the mood:
  funny -> laughing or cryinglaugh; impressive -> hype or slowclap; a fail or bad play -> facepalm (never hype on a fail); sarcastic -> slowclap.
Return JSON {{"mood": "funny|impressive|fail|sarcastic|chaotic", "segments": [{{"start": 0, "end": 3, "pose": "thinking", "climax": false}}, ...]}}
Transcript (times are seconds into the clip):
""" + '\n'.join(lines)[:6000])['segments']
    except Exception as e:
        print('  (mascot plan: AI unavailable, using fallback:', str(e)[:60], ')')
    ok = []
    for s in segs or []:
        try: ok.append({'start': float(s['start']), 'end': float(s['end']), 'pose': s['pose'] if s['pose'] in have else None, 'climax': bool(s.get('climax'))})
        except Exception: pass
    if not ok or abs(ok[-1]['end'] - dur) > 3:     # fallback: varied, mood-neutral timeline with a climax ~70% through
        ok, t, climax_at = [], 0.0, dur * 0.7
        while t < dur - 0.5:
            L = rnd.uniform(2.0, 3.6)
            if t <= climax_at < t + L and not any(s['climax'] for s in ok):
                ok.append({'start': t, 'end': min(dur, t + 1.4), 'pose': rnd.choice([p for p in ('laughing', 'cryinglaugh') if p in have]), 'climax': True}); t += 1.4; continue
            ok.append({'start': t, 'end': min(dur, t + L), 'pose': rnd.choice([p for p in CALM + POINT + TENSE if p in have]), 'climax': False}); t += L
    if sum(s['climax'] for s in ok) != 1:          # exactly one climax: keep the AI's first (or make the ~70% segment it)
        first = next((s for s in ok if s['climax']), None) or min(ok, key=lambda s: abs((s['start'] + s['end']) / 2 - dur * 0.7))
        for s in ok: s['climax'] = s is first
    seen_climax = False
    for i, s in enumerate(ok):                     # big reactions ONLY at the climax; calm "aftermath" after it; no back-to-back repeats
        prev = ok[i - 1]['pose'] if i else None
        if s['climax']:
            seen_climax = True
            if s['pose'] not in BIG: s['pose'] = None
        elif s['pose'] in BIG or (seen_climax and s['pose'] not in CALM):
            s['pose'] = rnd.choice([p for p in CALM if p in have and p != prev]) if seen_climax else None
        prev2 = ok[i - 2]['pose'] if i > 1 else None
        if s['pose'] is None or s['pose'] in (prev, prev2):
            pool = [p for p in (BIG if s['climax'] else CALM + POINT + TENSE) if p in have and p not in (prev, prev2)] or \
                   [p for p in (BIG if s['climax'] else CALM + POINT + TENSE) if p in have and p != prev]
            s['pose'] = rnd.choice(pool)
    ok[0]['start'] = 0.0; ok[-1]['end'] = dur
    return ok


def outlined(im, px=7):
    """White sticker outline + soft shadow so the mascot reads on any background (dark footage included)."""
    pad = px * 3; a = im.getchannel('A')
    big = Image.new('L', (im.width + 2 * pad, im.height + 2 * pad), 0); big.paste(a, (pad, pad))
    ring = big.filter(ImageFilter.MaxFilter(px * 2 + 1)).point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.GaussianBlur(0.8))
    shadow = big.filter(ImageFilter.MaxFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(8)).point(lambda v: int(v * 0.55))
    out = Image.new('RGBA', big.size, (0, 0, 0, 0))
    out.paste((0, 0, 0, 255), (6, 10), shadow)                 # shadow, offset down-right
    out.paste((255, 255, 255, 255), (0, 0), ring)              # white outline
    out.alpha_composite(im, (pad, pad))
    return out


def ease_out_back(x):
    c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def apply(base, words, out, mascot_dir, seed='x'):
    dur = duration(base)
    have = {f[:-4] for f in os.listdir(mascot_dir) if f.endswith('.png')}
    segs = plan(words, dur, have, seed)
    corner = pick_corner(base, dur); cx0, cy0 = CORNERS[corner]
    imgs = {}
    for p in {s['pose'] for s in segs}:
        im = Image.open(os.path.join(mascot_dir, p + '.png')).convert('RGBA')
        s = min(SIZE_H * 2.2 / im.height, MAX_W * 2.2 / im.width); im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        imgs[p] = outlined(im)
    print(f'  mascot: {corner} corner · ' + ' → '.join(s['pose'] + ('★' if s['climax'] else '') for s in segs), flush=True)
    enc = subprocess.Popen([FFMPEG, '-y', '-loglevel', 'error', '-i', base, '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                            '-filter_complex', '[0:v][1:v]overlay=0:0:shortest=1', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
                            '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    blank = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for f in range(int(dur * FPS)):
        t = f / FPS
        seg = next((s for s in segs if s['start'] <= t < s['end']), segs[-1])
        im = imgs[seg['pose']]; base_s = min(SIZE_H / im.height, MAX_W / im.width)
        lt = t - seg['start']; scale = 1.0; mx, my = 0.0, 0.0
        if lt < 0.28: scale = 0.55 + 0.45 * ease_out_back(lt / 0.28)                  # pop in with a little overshoot
        scale *= 1 + 0.025 * math.sin(t * 5.2)                                       # idle "breathing" bounce
        if seg['climax']:                                                            # climax: scale way up toward the centre, then back
            L = seg['end'] - seg['start']; up = min(1.0, lt / 0.22) if lt < L - 0.3 else max(0.0, (L - lt) / 0.3)
            k = ease_out_back(up) if up < 1 else 1.0
            scale *= 1 + 1.05 * k; mx = (W / 2 - (cx0 + MAX_W / 2)) * 0.35 * k; my = 120 * k
        if seg['end'] - t < 0.07 and seg is not segs[-1]: scale *= 0.82               # tiny pop-out right before the next pose
        w2, h2 = max(1, int(im.width * base_s * scale)), max(1, int(im.height * base_s * scale))
        frame = blank.copy(); sp = im.resize((w2, h2), Image.BILINEAR)
        ax = int(cx0 + MAX_W / 2 + mx - w2 / 2)
        ay = int(cy0 + my) if corner.startswith('top') else int(cy0 + SIZE_H + my - h2)   # top corners grow DOWN (never over the hook); others hop from the feet
        frame.alpha_composite(sp, (max(0, min(W - w2, ax)), max(0, min(H - h2, ay))))
        enc.stdin.write(frame.tobytes())
    enc.stdin.close(); enc.wait()
    return {'corner': corner, 'segments': segs}

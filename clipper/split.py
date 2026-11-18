#!/usr/bin/env python3
"""Split-screen clip editor (the format top streamer clip pages use):
   hook line on top · streamer face cam big · gameplay below · word-by-word captions in the middle.

   .venv/bin/python split.py jobs.json
   jobs.json: [{"src": "work/x/src1.mp4", "words": "work/x/words1.json", "start": 26, "end": 58,
                "hook": "Big Smoke broke into Kai's house 💀", "out": "out/x/01_big_smoke.mp4",
                "cam": [0, 0.244, 0.195, 0.194]}]   # face cam box as fractions of the frame: x, y, w, h
"""
import json, os, random, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clip import FFMPEG, clean

ROOT = os.path.dirname(os.path.abspath(__file__))
KAI_CAM = [0.0, 0.244, 0.195, 0.194]          # Kai's Twitch layout (top-left box)
# each clip page's own mascot (original characters we own) — makes every clip an original edit
MASCOT = {'gta6physix': 'dummy', 'vicecityrp': 'raccoon', 'pulsevice': 'robot', 'kai': 'dog', 'adin': 'fox', 'n3on': 'cat'}


def t(x): return f'{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}'


def ass_file(words, start, end, hook, path, cap_y=905):
    head = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n'
            'Style: Cap,Arial Black,78,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,7,2,5,90,140,0\n'
            'Style: Hook,Arial Black,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,4,1,8,70,70,255\n\n'
            '[Events]\nFormat: Layer, Start, End, Style, MarginL, MarginR, MarginV, Text\n')
    hook = ''.join(ch for ch in hook if ord(ch) < 0x2000).strip()   # the caption font can't draw emoji
    ev = [f'Dialogue: 1,{t(0)},{t(end - start)},Hook,0,0,0,{hook}']
    ws = [w for w in words if w['e'] > start and w['s'] < end]
    chunks, cur = [], []
    for w in ws:
        cur.append(w)
        if len(cur) == 3 or w['w'][-1:] in '.!?,': chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    cur = 0.0                                     # end of the last caption shown; nothing may start before it
    for ci, c in enumerate(chunks):
        nxt = (chunks[ci + 1][0]['s'] - start) if ci + 1 < len(chunks) else end - start
        s1 = min(c[-1]['e'] - start + 0.15, end - start, max(nxt, c[-1]['e'] - start))
        for k, w in enumerate(c):                 # current word highlighted yellow
            ws0 = max(w['s'] - start, cur, 0)
            ws1 = (c[k + 1]['s'] - start) if k + 1 < len(c) else s1
            ws1 = min(max(ws1, ws0 + 0.05), end - start)
            if ws1 <= ws0: continue
            cur = ws1
            txt = ' '.join(('{\\c&H00FFFF&}' + clean(x['w']).upper() + '{\\c&HFFFFFF&}') if j == k else clean(x['w']).upper()
                           for j, x in enumerate(c))
            ev.append(f'Dialogue: 0,{t(ws0)},{t(ws1)},Cap,0,0,0,{{\\pos(540,{cap_y})}}{txt}')
    open(path, 'w').write(head + '\n'.join(ev) + '\n')


def render(j):
    x, y, w, h = j.get('cam', KAI_CAM)
    words = json.load(open(os.path.join(ROOT, j['words']))) if j.get('words') else []
    ass = os.path.join(ROOT, j['out'] + '.ass'); os.makedirs(os.path.dirname(ass), exist_ok=True)
    ass_file(words, j['start'], j['end'], j['hook'], ass, 1170 if j.get('layout') == 'full' else 1028)
    # canvas 1080x1920 (TikTok safe zones): top 0-250 left clear for TikTok's search bar/tabs · hook text 255-415 · face cam 1080x608 at y=420 · gameplay 1080x892 at y=1028 · captions on the seam; right 140px kept clear of the like/comment buttons
    if j.get('layout') == 'full':   # whole frame is the camera (IRL): big center crop under the hook
        cx = j.get('cx', 0.5)   # where to center the crop (0 = left edge, 1 = right edge)
        # tighter frame (cuts corner logos/overlays) + a slow push-in zoom through the clip: real motion, not a static crop
        vf = (f'[0:v]fps=30,split[m][b];[m]crop=ih*0.69:ih*0.92:max(0\,min(iw-ih*0.69\,iw*{cx}-ih*0.345)):ih*0.04,scale=1080:1440,setsar=1,'
              f"zoompan=z='min(1+0.0016*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1440:fps=30[v];"
              f'[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,scale=1080:1920,eq=brightness=-0.15:saturation=1.2,setsar=1,fps=30[bg];'
              f"[bg][v]overlay=0:420:shortest=1,ass='{ass}'")
    else:
      vf = (f'[0:v]fps=30,split=3[c][g][b];'
          f'[c]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=1080:608,setsar=1[cam];'
          f'[g]crop=ih*1.211:ih:(iw-ih*1.211)/2+iw*0.04:0,scale=1080:892,setsar=1[game];'
          f'[b]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,scale=1080:1920,eq=brightness=-0.12:saturation=1.25,setsar=1,fps=30[bg];[bg][cam]overlay=0:420:shortest=1[a];[a][game]overlay=0:1028,'
          f"ass='{ass}'")
    # ---- page mascot (new system): rendered in a second pass by mascot_anim — whole clip, clearest corner, pose timeline ----
    extra_in = []
    m = None   # old start/end overlay disabled
    final_out = os.path.join(ROOT, j['out']); mascot_dir = os.path.join(ROOT, 'mascots', MASCOT.get(j.get('mascot') or '', '') or '_')
    use_anim = bool(j.get('mascot')) and os.path.isdir(mascot_dir)
    if use_anim: j = dict(j, out=j['out'] + '.base.mp4')
    if m and os.path.isdir(os.path.join(ROOT, 'mascots', m)):
        dur = float(j['end']) - float(j['start'])
        rnd = random.Random(j['out'])                                   # same clip -> same poses (re-renders stay identical)
        have = lambda n: n and os.path.exists(os.path.join(ROOT, 'mascots', m, n + '.png'))
        r1 = j.get('react_start') if have(j.get('react_start')) else rnd.choice(['shocked', 'pointing'])   # the AI picks a reaction that fits the moment
        r2 = j.get('react_end') if have(j.get('react_end')) else rnd.choice(['laughing', 'hype'])
        p1 = os.path.join(ROOT, 'mascots', m, r1 + '.png'); p2 = os.path.join(ROOT, 'mascots', m, r2 + '.png')
        extra_in = ['-loop', '1', '-t', f'{dur:.2f}', '-i', p1, '-loop', '1', '-t', f'{dur:.2f}', '-i', p2]
        a0, a1, b0 = 0.15, min(2.0, dur * 0.3), max(dur - 1.8, dur * 0.6)
        mx = lambda t0: f"if(lt(t-{t0}\\,0.22)\\,-w+(t-{t0})/0.22*(w+24)\\,24)"   # quick slide in from the left edge
        vf += (f"[pre];[1:v]scale=-1:400,format=rgba[m1];[2:v]scale=-1:400,format=rgba[m2];"
               f"[pre][m1]overlay=x='{mx(a0)}':y=1290:enable='between(t\\,{a0}\\,{a1:.2f})'[p1];"
               f"[p1][m2]overlay=x='{mx(round(b0, 2))}':y=1290:enable='between(t\\,{b0:.2f}\\,{dur:.2f})'")
    subprocess.run(['nice', '-n', '10', FFMPEG, '-y', '-loglevel', 'error', '-ss', str(j['start']), '-to', str(j['end']),
                    '-i', os.path.join(ROOT, j['src'])] + extra_in + ['-filter_complex', vf, '-r', '30',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '24', '-maxrate', '4M', '-bufsize', '8M', '-pix_fmt', 'yuv420p', '-tag:v', 'avc1',
                    '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-af', 'aresample=async=1:first_pts=0,loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-use_editlist', '0', '-movflags', '+faststart', os.path.join(ROOT, j['out'])], check=True)
    if use_anim:
        try:
            import mascot_anim
            wp = j.get('mwords') or j.get('words')
            allw = json.load(open(os.path.join(ROOT, wp))) if wp else []
            s0, s1 = float(j['start']), float(j['end'])
            rel = [{'w': w['w'], 's': round(w['s'] - s0, 2), 'e': round(w['e'] - s0, 2)} for w in allw if w['e'] > s0 and w['s'] < s1]
            mascot_anim.apply(os.path.join(ROOT, j['out']), rel, final_out, mascot_dir, seed=final_out)
            os.remove(os.path.join(ROOT, j['out']))
        except Exception as e:      # never lose the clip over the mascot
            print('  mascot failed, posting without it:', str(e)[:100], flush=True); os.replace(os.path.join(ROOT, j['out']), final_out)
    print('✅', final_out, flush=True)


if __name__ == '__main__':
    for j in json.load(open(sys.argv[1])): render(j)

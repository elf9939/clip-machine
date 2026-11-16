#!/usr/bin/env python3
"""Split-screen clip editor (the format top streamer clip pages use):
   hook line on top · streamer face cam big · gameplay below · word-by-word captions in the middle.

   .venv/bin/python split.py jobs.json
   jobs.json: [{"src": "work/x/src1.mp4", "words": "work/x/words1.json", "start": 26, "end": 58,
                "hook": "Big Smoke broke into Kai's house 💀", "out": "out/x/01_big_smoke.mp4",
                "cam": [0, 0.244, 0.195, 0.194]}]   # face cam box as fractions of the frame: x, y, w, h
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clip import FFMPEG, clean

ROOT = os.path.dirname(os.path.abspath(__file__))
KAI_CAM = [0.0, 0.244, 0.195, 0.194]          # Kai's Twitch layout (top-left box)


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
        vf = (f'[0:v]fps=30,split[m][b];[m]crop=ih*0.75:ih:max(0\,min(iw-ih*0.75\,iw*{cx}-ih*0.375)):0,scale=1080:1440,setsar=1[v];'
              f'[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,scale=1080:1920,eq=brightness=-0.15:saturation=1.2,setsar=1,fps=30[bg];'
              f"[bg][v]overlay=0:420:shortest=1,ass='{ass}'")
    else:
      vf = (f'[0:v]fps=30,split=3[c][g][b];'
          f'[c]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=1080:608,setsar=1[cam];'
          f'[g]crop=ih*1.211:ih:(iw-ih*1.211)/2+iw*0.04:0,scale=1080:892,setsar=1[game];'
          f'[b]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,scale=1080:1920,eq=brightness=-0.12:saturation=1.25,setsar=1,fps=30[bg];[bg][cam]overlay=0:420:shortest=1[a];[a][game]overlay=0:1028,'
          f"ass='{ass}'")
    subprocess.run(['nice', '-n', '10', FFMPEG, '-y', '-loglevel', 'error', '-ss', str(j['start']), '-to', str(j['end']),
                    '-i', os.path.join(ROOT, j['src']), '-filter_complex', vf, '-r', '30',
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '24', '-maxrate', '4M', '-bufsize', '8M', '-pix_fmt', 'yuv420p', '-tag:v', 'avc1',
                    '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-af', 'aresample=async=1:first_pts=0,loudnorm=I=-14:TP=-1.5:LRA=11',
                    '-use_editlist', '0', '-movflags', '+faststart', os.path.join(ROOT, j['out'])], check=True)
    print('✅', j['out'], flush=True)


if __name__ == '__main__':
    for j in json.load(open(sys.argv[1])): render(j)

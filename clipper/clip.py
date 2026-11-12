#!/usr/bin/env python3
"""Free clip machine: stream VOD -> transcript -> (Claude picks moments) -> vertical captioned clips.

  1) prep:   .venv/bin/python clip.py prep <url> [--from 1:00:00 --to 1:45:00] [--name kai_nov10]
             downloads that part of the stream, transcribes it -> work/<name>/transcript.txt
  2) Claude reads transcript.txt and writes work/<name>/picks.json:
             [{"start": 123.4, "end": 168.0, "title": "Kai loses it at ..."}]
  3) render: .venv/bin/python clip.py render <name>
             -> out/<name>/01_<title>.mp4 (1080x1920, blurred background, big burned-in captions)
"""
import argparse, json, os, re, subprocess, sys

BIN = os.path.expanduser('~/.local/bin')
YTDLP, FFMPEG = f'{BIN}/yt-dlp', f'{BIN}/ffmpeg'
ROOT = os.path.dirname(os.path.abspath(__file__))


os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')  # static ffmpeg has no CA bundle of its own


def sh(cmd):
    print('$', ' '.join(cmd)[:200], flush=True)
    subprocess.run(['nice', '-n', '10'] + cmd, check=True)


def ts(sec):
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f'{h}:{m:02d}:{sec % 60:05.2f}'


def prep(a):
    work = os.path.join(ROOT, 'work', a.name); os.makedirs(work, exist_ok=True)
    video = os.path.join(work, 'source.mp4')
    if not os.path.exists(video):
        cmd = [YTDLP, '-f', 'bv*[height<=720]+ba/b[height<=720]/b', '--merge-output-format', 'mp4',
               '--ffmpeg-location', BIN, '--js-runtimes', 'node:' + os.path.expanduser('~/.local/bin/node'), '-o', video, a.url]
        if a.frm or a.to:
            cmd[1:1] = ['--download-sections', f'*{a.frm or "0"}-{a.to or "inf"}']
        sh(cmd)
    audio = os.path.join(work, 'audio.wav')
    if not os.path.exists(audio):
        sh([FFMPEG, '-y', '-loglevel', 'error', '-i', video, '-ac', '1', '-ar', '16000', audio])
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device='cpu', compute_type='int8', cpu_threads=4)
    segs, _ = model.transcribe(audio, word_timestamps=True, vad_filter=True, language='en')
    words, lines = [], []
    for s in segs:
        lines.append(f'[{ts(s.start)} - {ts(s.end)}] {s.text.strip()}')
        words += [{'w': w.word.strip(), 's': round(w.start, 2), 'e': round(w.end, 2)} for w in (s.words or [])]
        print(lines[-1][:120], flush=True)
    json.dump(words, open(os.path.join(work, 'words.json'), 'w'))
    open(os.path.join(work, 'transcript.txt'), 'w').write('\n'.join(lines))
    print(f'\nTranscript ready: {work}/transcript.txt  ({len(lines)} lines). Next: write picks.json, then render.')


BLEEP = re.compile(r"\b(n+i+g+(a+|e+r+|g+a+|g+e+r+|gaz?|guh)s?|f+u+c+k\w*|b+i+t+c+h\w*|s+h+i+t+\w*|p+u+s+s+y|d+i+c+k\w*|c+u+n+t|f+a+g+\w*|r+e+t+a+r+d\w*|w+h+o+r+e\w*)\b", re.I)


def clean(t):
    """Star out slurs/heavy swearing in captions (TikTok/YouTube limit reach on them): fuck -> f**k."""
    t = re.sub(r'(?i)(mother)f+u+c+k', lambda m: m.group(1) + 'f**k', t)
    return BLEEP.sub(lambda m: m.group(0)[0] + '*' * (len(m.group(0)) - 2) + m.group(0)[-1], t)


def ass_captions(words, start, end, path):
    """Big centered 2-3 word captions, white with thick black outline, current chunk only."""
    chunk, chunks = [], []
    for w in words:
        if w['e'] <= start or w['s'] >= end: continue
        chunk.append(w)
        if len(chunk) == 3 or re.search(r'[.!?,]$', w['w']):
            chunks.append(chunk); chunk = []
    if chunk: chunks.append(chunk)
    t = lambda x: f'{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}'
    head = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV\n'
            'Style: Cap,Arial Black,92,&H00FFFFFF,&H00000000,&H64000000,1,7,2,5,0\n\n[Events]\n'
            'Format: Layer, Start, End, Style, Text\n')
    ev = []
    for c in chunks:
        s, e = max(c[0]['s'] - start, 0), min(c[-1]['e'] - start, end - start)
        text = clean(' '.join(x['w'] for x in c)).upper().replace('{', '').replace('}', '')
        ev.append(f'Dialogue: 0,{t(s)},{t(e)},Cap,{{\\pos(540,1300)}}{text}')
    open(path, 'w').write(head + '\n'.join(ev) + '\n')


def render(a):
    work = os.path.join(ROOT, 'work', a.name)
    picks = json.load(open(os.path.join(work, 'picks.json')))
    words = json.load(open(os.path.join(work, 'words.json')))
    out = os.path.join(ROOT, 'out', a.name); os.makedirs(out, exist_ok=True)
    for i, p in enumerate(picks, 1):
        slug = re.sub(r'[^a-z0-9]+', '_', p['title'].lower()).strip('_')[:50]
        dst = os.path.join(out, f'{i:02d}_{slug}.mp4')
        ass = os.path.join(work, f'cap{i:02d}.ass')
        ass_captions(words, p['start'], p['end'], ass)
        # 9:16: blurred zoomed copy as background, full 16:9 frame in the middle, captions under it
        vf = ('[0:v]split[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2,eq=brightness=-0.15[bg];'
              '[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2-120,ass=' + ass.replace(':', r'\:'))
        sh([FFMPEG, '-y', '-loglevel', 'error', '-ss', str(p['start']), '-to', str(p['end']),
            '-i', os.path.join(work, 'source.mp4'), '-filter_complex', vf,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-c:a', 'aac', '-b:a', '160k',
            '-movflags', '+faststart', dst])
        print('✅', dst, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    p1 = sp.add_parser('prep'); p1.add_argument('url'); p1.add_argument('--from', dest='frm')
    p1.add_argument('--to'); p1.add_argument('--name', default='clip'); p1.add_argument('--model', default='small.en')
    p2 = sp.add_parser('render'); p2.add_argument('name')
    a = ap.parse_args(); (prep if a.cmd == 'prep' else render)(a)

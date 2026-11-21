#!/usr/bin/env python3
"""Clip quality inspector (like TrendTok / HypeRadar pre-post scoring, but it also fixes the clip).
The AI watches the finished clip and scores hook, visual, audio, content, engagement (0-100), lists problems,
and suggests fixes: a trim of a slow start/end, a stronger hook, a tighter caption.

  python3 review.py clip.mp4 "hook text" "caption"     # prints the JSON verdict
"""
import json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gemini import ask_json_video

FFMPEG = os.path.expanduser('~/.local/bin/ffmpeg')
if not os.path.exists(FFMPEG): FFMPEG = 'ffmpeg'

PROMPT = """You are a strict TikTok growth editor reviewing a finished 9:16 clip for a fan clip page BEFORE it is posted.
The on-screen hook is: "{hook}"
The caption is: "{caption}"
Watch the whole clip and judge it the way TikTok's algorithm does: will a stranger stop scrolling in the first 2 seconds and watch to the end?

Score each 0-100:
- hook: do the first 2 seconds (picture + hook text + first words) create curiosity or show something wild right away?
- visual: is the subject clearly visible and well framed, nothing important cut off or hidden behind text, readable captions?
- audio: clear speech, no long silence, not drowned by music, no distortion?
- content: is there a real payoff (funny, shocking, hype, a story that lands) and does it make sense with no context?
- engagement: would people comment, share or rewatch it?
- originality: TikTok marks clips as "unoriginal" (not shown on For You) when they look copied from another source without creative edits.
  Score LOW if you see a watermark or logo (Kick/Twitch/YouTube logos, another clipping page's handle or branding, burned-in subtitles in a different style),
  if it looks like a re-upload of an already-edited/viral clip or compilation, or if it is mostly unchanged footage. Score HIGH for fresh raw stream moments with our own hook + captions.
- burned_subs: true if the ORIGINAL footage already has subtitles burned in (text lines of speech, any language), not counting our own yellow/white word captions or the hook at the top.
- fyp_safe: TikTok hides videos from the For You feed for "Regulated Goods" and "Sensitive and Mature Themes". Set "regulated": true if weapons are the FOCUS
  (gun shop/ammo store, weapon menu or wheel, buying/listing/showing off guns, a gun pointed at the camera), or it shows/talks about drugs, alcohol, vaping/smoking,
  gambling/casino, or strip clubs. Ordinary quick gameplay with shooting in the background is NOT regulated. Set "mature": true for sexual content or jokes,
  real-world violence, self-harm, or dangerous stunts people could copy. Give a short "risk_reason".
overall = your honest overall 0-100 (not just the average). verdict: "post" (good as is), "fix" (good after the fixes below), or "skip" (weak, would hurt the page).

Fixes (only suggest what would clearly help):
- trim_start: seconds to cut from the START if it opens slow (0 if fine). trim_end: seconds to cut from the END if it drags after the payoff (0 if fine).
- hook: a better on-screen hook (max 55 characters, no emoji, true to what happens) or the same one if it's already strong.
- caption: a better caption keeping the same format (1 punchy line, a follow line, 4-5 hashtags) or the same one.
Return JSON only:
{{"scores":{{"hook":0,"visual":0,"audio":0,"content":0,"engagement":0,"originality":0}},"overall":0,"verdict":"post|fix|skip","watermark":false,
"regulated":false,"mature":false,"burned_subs":false,"risk_reason":"","issues":["short problem notes"],"fixes":{{"trim_start":0,"trim_end":0,"hook":"...","caption":"..."}}}}"""


def proxy(path):
    """Small copy for the AI to watch (keeps the request well under the size limit)."""
    out = tempfile.mktemp(suffix='.mp4')
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', path, '-t', '20', '-vf', 'scale=320:-2', '-r', '8', '-c:v', 'libx264', '-crf', '34', '-preset', 'veryfast',
                    '-c:a', 'aac', '-b:a', '32k', '-ac', '1', out], check=True)   # cost: 20s max, 320px, 8fps (video tokens are the main Gemini cost)
    return out


def review(path, hook, caption, need_gta6=False):
    p = proxy(path)
    extra = ('\nALSO return "is_gta6": true if this is GTA 6 (Grand Theft Auto VI) — gameplay or a streamer reacting while GTA 6 is on screen '
             '(new Vice City/Leonida map, Jason/Lucia, GTA 6 HUD/intro). false if it is GTA 5, another game, a trailer, leaked/old footage, or nothing GTA 6 is on screen.') if need_gta6 else ''
    try: return ask_json_video(p, PROMPT.format(hook=hook.replace('"', "'"), caption=caption.replace('"', "'")) + extra)
    finally: os.remove(p)


if __name__ == '__main__':
    print(json.dumps(review(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '', sys.argv[3] if len(sys.argv) > 3 else ''), indent=1))

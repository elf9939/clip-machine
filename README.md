# Clip machine (Jarvis)
Runs daily on GitHub Actions: pulls trending streamer clips, transcribes them, lets Gemini pick + title the best ones
(rules in `clipper/brain/`), cuts 9:16 clips, sends them to Post Hub (auto-schedules warmed pages), then posts a report
notification. Secrets: `PH_AUTOMATION_KEY`, `GEMINI_API_KEY`.

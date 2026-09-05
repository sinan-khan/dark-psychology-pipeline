# Dark Psychology Shorts — Automated Pipeline

Fully automated 35-55s vertical Shorts. You only supply the visual clip
library — topic, script, English voiceover, and captions are generated
each run.

## How it works

1. **visual_analyzer.py** — tags everything in `input/visuals/` from filenames
2. **topic_script_engine.py** — Gemini (free tier) picks a topic and writes a
   Hook → Body → Example → Ending script as JSON, including which word to
   highlight per line
3. **tts_engine.py** — `edge-tts` (free, no key) generates the English
   voiceover *and* returns word-level timestamps in the same call
4. **scene_planner.py** — matches each script line to your best-fitting clip
5. **caption_engine.py** — builds white/yellow karaoke-style `.ass` captions
   from the word timestamps
6. **compose.py** — FFmpeg assembles clips + captions + voiceover + ducked
   background music into the final MP4
7. **quality_check.py** — verifies resolution, audio, and duration before
   the run is considered successful

`main.py` runs all of this in order.

## Setup (all through GitHub's web UI)

1. Create a new repo and upload this whole folder to it.
2. Get a free Gemini API key: https://aistudio.google.com/apikey
3. In the repo: **Settings → Secrets and variables → Actions → New repository
   secret** — name it `GEMINI_API_KEY`, paste your key.
4. Drop your clips/images into `input/visuals/` (name them descriptively —
   e.g. `person_thinking_alone.mp4`, `couple_arguing_kitchen.mp4` — the
   filename *is* the tag database).
5. Drop 3-5 royalty-free background tracks into `input/music/` (the
   Music Engine picks one at random each run).
6. Go to the **Actions** tab → "Generate Dark Psychology Short" → **Run
   workflow** to test it manually. On success it commits the finished MP4
   into `output/` and also attaches it as a downloadable run artifact.
7. Once you're happy with a few test runs, the `schedule:` cron in
   `.github/workflows/generate_video.yml` will run it automatically —
   currently set to daily at 14:00 UTC, edit that line for your cadence.

## Notes / tuning

- **Highlight word accuracy**: the script engine picks the highlight word
  itself as part of the JSON it returns, so caption quality depends on the
  prompt in `topic_script_engine.py` — tune `SYSTEM_PROMPT` there if
  highlights feel off.
- **Voice**: `config/style.json` → `voice.name`. Full free voice list:
  run `edge-tts --list-voices` locally, or check the edge-tts docs. Try
  `en-US-GuyNeural` or `en-GB-RyanNeural` for a different tone.
- **Visual matching** is pure keyword overlap (no ML) — if a scene keeps
  getting a bad match, it's almost always because no clip filename shares a
  tag with `visual_tags` in the script. Add more descriptively-named clips.
- **Topic repeats**: `config/used_topics.json` tracks covered topics so the
  Script Engine avoids repeating itself — commit this file back to the repo
  (the workflow already does).
- **Copyright**: this pipeline is built for footage you own or have rights
  to use, and royalty-free/licensed music — swap in anything else at your
  own risk.

## Local testing (optional)

If you ever want to test outside GitHub Actions:

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here
python main.py test_run
```

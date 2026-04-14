# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Reel Maker Studio — a Python pipeline that turns pasted Reddit posts (or arbitrary text) into vertical 1080x1920 short-form videos with karaoke subtitles, a Reddit-style intro card, background gameplay footage, and background music. It auto-splits long stories into "Part N" reels.

Input is supplied by the user via the Web UI (raw Reddit copy-paste gets parsed client-side, screenshot OCR via OpenRouter, or manual typing) or via the CLI `--text` flag. There is no Reddit scraping — PRAW was removed; text must be provided.

## Running

All commands assume the working directory is the project root. There is no test suite, linter, or build step configured.

- **Web UI (primary entry point):** `start_app.bat` — uses `.venv\Scripts\python.exe`, `cd`s to `src/`, and runs `app.py`. FastAPI serves on `http://localhost:8000` with `--reload`.
- **CLI:** `python src/main.py` (scrape Reddit) or `python src/main.py --text "..."` or `python src/main.py --skip-scrape` to reuse the cached story at `temp/last_story.txt`.
- **Install deps:** `pip install -r requirements.txt`. FFmpeg is bundled via `imageio-ffmpeg` — no system FFmpeg install needed.
- **Logs:** `app.py` redirects stdout/stderr to `src/app_debug.log`. FFmpeg output goes to `ffmpeg_last_run.log` in the CWD of whoever invoked the pipeline (root when run via `start_app.bat`, `src/` when invoked differently — inconsistent, watch for both).

## Architecture

The pipeline is a linear chain of modules in `src/`, orchestrated by `run_pipeline()` in `main.py`. `app.py` is a thin FastAPI wrapper that calls the same `run_pipeline()` in a `BackgroundTasks` thread — **any change to the pipeline signature must be kept in sync with `run_pipeline_wrapper` in `app.py`**.

Stage order (all stages write intermediate artifacts to `temp/`):

1. **Acquire text** — passed into `run_pipeline(text=...)` by the web form or CLI `--text`. Body is cached to `temp/last_story.txt` so `--skip-scrape` can reuse it.
2. **TTS** — `tts.py` (`TTSEngine`, edge-tts). Produces `tts_voice.mp3` for the body and `tts_title.mp3` for the intro card voiceover.
3. **Intro card render** — `reddit_card.py` (`RedditCardRenderer`) renders an HTML → PNG Reddit post card used as an overlay during the title audio.
4. **Transcribe** — `transcription.py` (`Transcriber`, faster-whisper) returns `TranscriptionResult` with word-level timestamps. `transcription.to_ass(...)` emits a libass `.ass` subtitle file with the karaoke styling applied from `style_config`.
5. **Part splitting** — `main.py` scans the word list for sentence-ending punctuation to find split boundaries whenever total audio > `max_duration` (default 60s). Each subsequent part **overlaps** with the previous part's final sentence (re-reads it) so the story flows. Non-final parts get a "Follow for Part N+1" overlay + TTS tail.
6. **Compose** — `processor.py` (`VideoProcessor.compose`) builds one monolithic FFmpeg command per part. Inputs: looping BG video, optional intro TTS, body TTS (with `-ss`/`-t` slicing), optional looping BG music, optional follow TTS, optional looping intro-card PNG. The filter_complex:
   - Scales/crops BG video to target resolution, applies `setpts` for `video_speed`, then burns in subtitles via the `ass=` filter.
   - Overlays the Reddit card only for `t <= intro_duration` (Part 1 only).
   - Concatenates intro+body TTS, mixes in BG music at `BG_MUSIC_VOLUME`, and optionally the follow audio delayed to the end.
   - **Subtitle timing gotcha:** `to_ass` is called with `intro_duration` so subtitle timestamps are offset past the intro card phase.

`utils.py` owns all paths (`ROOT_DIR`, `ASSETS_DIR`, `BG_VIDEOS_DIR`, `BG_MUSIC_DIR`, `OUTPUTS_DIR`, `TEMP_DIR`), env parsing, text cleaning, asset random-picking, and `generate_output_filename()` which preserves `_PartN` suffixes when truncating titles to 50 chars.

### Web UI surface (`src/app.py`)

FastAPI endpoints the frontend (`src/static/index.html` + `script.js`) consumes:

- `GET /api/voices` — filtered edge-tts voice list
- `GET /api/assets` — BG videos + music in `assets/`
- `POST /api/process` — kicks off `run_pipeline` as a background task (fire-and-forget; the UI auto-polls `/api/list_output_videos` every 5s for ~3 min after submit to surface the finished reel)
- `POST /api/generate_caption` / `POST /api/process_ocr` — OpenRouter-backed (caption uses `stepfun/step-3.5-flash:free`, OCR uses `google/gemini-2.0-flash-lite-preview-02-05:free`)
- `POST /api/generate_thumbnail` — `thumbnail.py` grabs a random BG frame and writes a styled `.jpg` into `src/static/` so the UI can load it immediately
- `POST /api/upload_instagram` — `instagrapi` Reel upload; session is cached at `src/ig_session.json` and rotated on auth failure

The primary one-click flow: paste a raw Reddit post into the Smart Paste textarea → client-side `parseRedditPaste()` in `script.js` extracts subreddit, age, username, title, score, comments, body → auto-fills all form fields + auto-focuses the Generate button. The last-used voice is persisted in `localStorage` key `reelmaker.lastVoice` so returning visits skip voice selection.

### Configuration (`.env`)

Loaded by both `app.py` (with `override=True`) and `utils.py`. Notable keys: `OPENROUTER_API_KEY`, `INSTAGRAM_USERNAME/PASSWORD`, `WHISPER_MODEL`, `DEVICE` (`cpu`/`cuda`), `VIDEO_CODEC` (`libx264` / `h264_nvenc`), `OUTPUT_RESOLUTION`, `MAX_DURATION_SECONDS`, `BG_MUSIC_VOLUME`, `VIDEO_BITRATE`, `TTS_VOICE`. Web UI form fields override env defaults per-request.

### Assets

- `assets/background_videos/*.mp4` — vertical loopable gameplay clips. The pipeline fails loudly if this dir is empty.
- `assets/bg_music/*.{mp3,wav,ogg,m4a}` — optional; silent if missing.
- `assets/outputs/*.mp4` — final rendered reels.

## Things to know before editing

- **One supported venv:** `.venv/` (Python 3.14) is the only supported environment for this repo.
- **`processor.py` re-picks BG music** on line ~126 via `pick_random_bg_music()` even when `bg_music_path` was already passed in, overriding the caller's selection. If you're touching music selection, this is almost certainly a bug to preserve-or-fix deliberately.
- **Windows path handling in FFmpeg:** the `.ass` subtitle path is passed as a POSIX-style relative path (`os.path.relpath(...).replace("\\", "/")`) because libass's `ass=` filter chokes on Windows backslashes and drive-letter colons. Preserve this when changing where subs are written.
- **No progress reporting**: `/api/process` returns immediately; the frontend just watches the outputs dir. Don't promise the user live progress without adding a channel.
- **`app.py` hijacks stdout/stderr on import** (writes to `app_debug.log`). If you add CLI tooling that also imports from `app`, expect silent consoles.
- **Stray temp files** like `src/reddit_reel_PartN_TEMP_MPY_wvf_snd.mp4` are leftover MoviePy artifacts from an earlier implementation — safe to ignore; not referenced by current code.

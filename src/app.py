import asyncio
import os
import base64
import uuid
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

from tts import TTSEngine
from main import run_pipeline
from thumbnail import ThumbnailProcessor
from utils import TEMP_DIR
import random

# Ensure directories exist
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# Redirect logs to file
log_file = open("app_debug.log", "a", encoding="utf-8", buffering=1)
import sys
sys.stdout = log_file
sys.stderr = log_file

PIPELINE_STATUS = {
    "job_id": None,
    "state": "idle",
    "error": None,
    "log_start": 0,
}

app = FastAPI(title="Reel Maker Studio")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_CAPTION_MODELS = [
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "stepfun/step-3.5-flash:free",
]
DEFAULT_OCR_MODELS = [
    "google/gemini-2.0-flash-lite-preview-02-05:free",
]


def get_openrouter_models(env_var: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(env_var, "").strip()
    if raw:
        models = [model.strip() for model in raw.split(",") if model.strip()]
        if models:
            return models
    return defaults


def openrouter_chat_completion(api_key: str, messages: list, models: list[str], timeout: int = 15) -> str:
    last_error = None

    for model in models:
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages
                },
                timeout=timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            last_error = e
            response = getattr(e, "response", None)
            response_text = response.text if response is not None else ""
            if response is not None and response.status_code == 404 and "No endpoints found" in response_text:
                print(f"OpenRouter model unavailable, trying next fallback: {model}")
                continue
            raise

    if last_error is not None:
        raise last_error

    raise RuntimeError("No OpenRouter models configured.")


@app.get("/", response_class=HTMLResponse)
async def read_index():
    """Serve the main UI."""
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/api/voices")
def get_voices():
    """Returns a list of all available English TTS voices."""
    engine = TTSEngine()
    # List voices returns strings like "en-US-ChristopherNeural  (Male)"
    voices = engine.list_voices(language_filter="en")
    
    # Parse them into a cleaner list of dicts for the frontend
    voice_data = []
    for v in voices:
        parts = v.split("  (")
        if len(parts) == 2:
            name_id = parts[0].strip()
            gender = parts[1].replace(")", "").strip()
            
            # Create a friendly display name (e.g. "Christopher (US)" instead of "en-US-ChristopherNeural")
            friendly = name_id.replace("Neural", "")
            if "en-" in friendly:
                lang, region, name = friendly.split("-", 2)
                friendly = f"{name} ({region})"
                
            voice_data.append({
                "id": name_id,
                "display": f"{friendly} - {gender}"
            })
            
    # Sort for better UI experience
    return {"voices": sorted(voice_data, key=lambda x: x["display"])}


@app.get("/api/assets")
def list_assets():
    """Returns lists of available background videos and music files."""
    from utils import BG_VIDEOS_DIR, BG_MUSIC_DIR
    
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    audio_exts = {'.mp3', '.wav', '.ogg', '.m4a'}
    
    videos = [f.name for f in BG_VIDEOS_DIR.iterdir() if f.suffix.lower() in video_exts]
    music = [f.name for f in BG_MUSIC_DIR.iterdir() if f.suffix.lower() in audio_exts]
    
    return {
        "videos": sorted(videos),
        "music": sorted(music)
    }


@app.post("/api/generate_caption")
async def generate_caption(text: str = Form(...)):
    """Generates an AI caption using OpenRouter with model fallbacks."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_openrouter_key_here":
        raise HTTPException(status_code=400, detail="Missing OpenRouter API Key in .env file.")
        
    prompt = f"You are a social media expert. Write a short, engaging viral caption for a short-form video (TikTok/Reel) based on the following story. Only provide the caption and a few relevant hashtags. Do not include extra conversational text.\n\nStory: {text[:2000]}"
    
    try:
        caption = openrouter_chat_completion(
            api_key=api_key,
            messages=[{"role": "user", "content": prompt}],
            models=get_openrouter_models("OPENROUTER_CAPTION_MODELS", DEFAULT_CAPTION_MODELS),
            timeout=15,
        )
        return {"caption": caption}
    except requests.exceptions.RequestException as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            err_msg += f" | Response: {e.response.text}"
        print(f"Caption API Error: {err_msg}")
        raise HTTPException(status_code=500, detail=f"API Error: {err_msg}")
    except Exception as e:
        print(f"Caption General Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate: {str(e)}")


@app.post("/api/process_ocr")
async def process_ocr(image: UploadFile = File(...)):
    """Extracts text from a screenshot using AI vision (OpenRouter)."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_openrouter_key_here":
        raise HTTPException(status_code=400, detail="Missing OpenRouter API Key in .env file.")

    # Read and encode the image
    content = await image.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image is too large. Please use an image under 10MB.")

    # Determine MIME type
    mime = image.content_type or "image/png"
    b64_data = base64.b64encode(content).decode("utf-8")
    data_url = f"data:{mime};base64,{b64_data}"

    prompt = (
        "You are an expert text extractor. Look at this screenshot of a Reddit post or social media story. "
        "Extract ONLY the story/body text content. Do NOT include usernames, subreddit names, upvote counts, "
        "timestamps, UI elements, or any metadata. Clean up the text: remove markdown artifacts, fix obvious "
        "OCR errors, and present the story as clean, readable paragraphs. If there is no readable story text, "
        "respond with exactly: NO_TEXT_FOUND"
    )

    try:
        extracted = openrouter_chat_completion(
            api_key=api_key,
            models=get_openrouter_models("OPENROUTER_OCR_MODELS", DEFAULT_OCR_MODELS),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }],
            timeout=30,
        )

        if extracted == "NO_TEXT_FOUND" or len(extracted) < 10:
            raise HTTPException(status_code=400, detail="Could not find readable story text in this image. Try a clearer screenshot.")

        return {"text": extracted}

    except requests.exceptions.RequestException as e:
        err_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            err_msg += f" | Response: {e.response.text}"
        print(f"OCR API Error: {err_msg}")
        raise HTTPException(status_code=500, detail=f"AI Vision API Error: {err_msg}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"OCR General Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")



@app.post("/api/process")
async def process_video(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    voice: str = Form(...),
    font_size: int = Form(110),
    font_color: str = Form("#FFD700"), # Gold default
    stroke_color: str = Form("#000000"),
    stroke_width: int = Form(3),
    max_duration: int = Form(60),
    video_bitrate: str = Form("50000k"),
    tts_rate: str = Form("+60%"),
    video_speed: float = Form(1.0),
    bg_video: str = Form("random"),
    bg_music: str = Form("random"),
    title: str = Form("reddit_reel"),
    # Reddit card metadata (optional — used for intro card overlay)
    subreddit: str = Form("AskReddit"),
    username: str = Form("u/user"),
    score: int = Form(0),
    num_comments: int = Form(0),
    post_age: str = Form("2d"),
):
    """Triggers the video generation pipeline in the background."""
    if PIPELINE_STATUS["state"] == "running":
        raise HTTPException(status_code=409, detail="A pipeline job is already running.")

    log_file.flush()
    job_id = uuid.uuid4().hex
    log_path = Path("app_debug.log")
    PIPELINE_STATUS.update({
        "job_id": job_id,
        "state": "queued",
        "error": None,
        "log_start": log_path.stat().st_size if log_path.exists() else 0,
    })

    print(f"Received request: font={font_size}, color={font_color}")
    
    style_config = {
        "Highlight": {
            "font_size": font_size,
            "color": font_color,
            "stroke_color": stroke_color,
            "stroke_width": stroke_width
        },
        "Follow": {
            "font_size": max(75, font_size - 10), # Slightly smaller
            "color": "#00AAFF", # Greenish-blue default for follow text
            "stroke_color": stroke_color,
            "stroke_width": stroke_width
        }
    }
    
    # We will pass the style_config into a heavily modified run_pipeline
    background_tasks.add_task(
        run_tracked_pipeline,
        job_id=job_id,
        text=text,
        title=title,
        voice=voice,
        style_config=style_config,
        max_duration=max_duration,
        video_bitrate=video_bitrate,
        tts_rate=tts_rate,
        video_speed=video_speed,
        bg_video=None if bg_video == "random" else bg_video,
        bg_music=None if bg_music == "random" else bg_music,
        subreddit=subreddit,
        username=username,
        score=score,
        num_comments=num_comments,
        post_age=post_age,
    )

    return {"status": "processing initiated", "job_id": job_id}


@app.get("/api/process_status")
async def process_status(job_id: str, offset: int = 0):
    """Returns current pipeline status and any new log output."""
    if not PIPELINE_STATUS["job_id"] or job_id != PIPELINE_STATUS["job_id"]:
        raise HTTPException(status_code=404, detail="Pipeline job not found.")

    log_file.flush()
    log_path = Path("app_debug.log")
    if not log_path.exists():
        return {
            "state": PIPELINE_STATUS["state"],
            "error": PIPELINE_STATUS["error"],
            "logs": "",
            "offset": max(0, offset),
        }

    base_offset = PIPELINE_STATUS["log_start"]
    current_size = log_path.stat().st_size
    read_start = min(base_offset + max(0, offset), current_size)

    with log_path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(read_start)
        logs = fh.read()

    return {
        "state": PIPELINE_STATUS["state"],
        "error": PIPELINE_STATUS["error"],
        "logs": logs,
        "offset": current_size - base_offset,
    }


@app.post("/api/generate_thumbnail")
async def create_thumbnail(
    thumbnail_text: str = Form(...),
    font_color: str = Form("#FFD700"),
    stroke_color: str = Form("#000000"),
    stroke_width: int = Form(3)
):
    """Generates a styled thumbnail from a random background video frame."""
    if not thumbnail_text.strip():
        raise HTTPException(status_code=400, detail="Thumbnail text cannot be empty.")
        
    # Resolve relative to project root (one level up from src)
    project_root = Path(__file__).parent.parent
    bg_dir = project_root / "assets" / "background_videos"
    
    if not bg_dir.exists() or not any(bg_dir.iterdir()):
        raise HTTPException(status_code=400, detail="No background videos found in assets/background_videos")
        
    valid_bgs = list(bg_dir.glob("*.mp4"))
    if not valid_bgs:
        raise HTTPException(status_code=400, detail="No .mp4 files found for background.")
        
    chosen_bg = random.choice(valid_bgs)
    
    style_config = {
        "color": font_color,
        "stroke_color": stroke_color,
        "stroke_width": stroke_width
    }
    
    output_filename = f"thumb_{random.randint(1000, 9999)}.jpg"
    # Save the thumbnail directly into the static dir so the UI can load it immediately
    output_path = STATIC_DIR / output_filename
    
    processor = ThumbnailProcessor()
    
    try:
        # Run in threadpool so ffmpeg doesn't block the async loop
        await asyncio.to_thread(processor.generate, chosen_bg, thumbnail_text, style_config, output_path)
        return {"thumbnail_url": f"/static/{output_filename}"}
    except Exception as e:
        print(f"Thumbnail API Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate thumbnail: {str(e)}")


@app.get("/api/list_output_videos")
def list_output_videos():
    """Returns a list of .mp4 files in the outputs directory, sorted newest first."""
    from utils import OUTPUTS_DIR
    video_exts = {'.mp4'}
    videos = []
    if OUTPUTS_DIR.exists():
        for f in OUTPUTS_DIR.iterdir():
            if f.suffix.lower() in video_exts:
                videos.append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    "modified": f.stat().st_mtime
                })
    # Sort by modified time, newest first
    videos.sort(key=lambda x: x["modified"], reverse=True)
    return {"videos": videos}


# --- Instagram Session Management ---
IG_SESSION_PATH = Path(__file__).parent / "ig_session.json"

def get_ig_client():
    """Get an authenticated Instagram client, using cached session if available."""
    from instagrapi import Client

    ig_user = os.getenv("INSTAGRAM_USERNAME", "").strip()
    ig_pass = os.getenv("INSTAGRAM_PASSWORD", "").strip()

    if not ig_user or not ig_pass:
        raise HTTPException(status_code=400, detail="Instagram credentials not configured. Add INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD to your .env file.")

    cl = Client()
    # Mimic a real device to reduce detection
    cl.delay_range = [1, 3]

    try:
        if IG_SESSION_PATH.exists():
            print("📱 Loading cached Instagram session...")
            cl.load_settings(IG_SESSION_PATH)
            cl.login(ig_user, ig_pass)
            # Verify the session is still valid
            try:
                cl.get_timeline_feed()
                print("✅ Instagram session is valid.")
            except Exception:
                print("⚠️ Cached session expired, doing fresh login...")
                cl = Client()
                cl.delay_range = [1, 3]
                cl.login(ig_user, ig_pass)
                cl.dump_settings(IG_SESSION_PATH)
        else:
            print("📱 Fresh Instagram login...")
            cl.login(ig_user, ig_pass)
            cl.dump_settings(IG_SESSION_PATH)
            print("✅ Logged in and session cached.")
    except Exception as e:
        print(f"❌ Instagram login failed: {e}")
        # Clean up bad session
        if IG_SESSION_PATH.exists():
            IG_SESSION_PATH.unlink()
        raise HTTPException(status_code=401, detail=f"Instagram login failed: {str(e)}")

    return cl


@app.post("/api/upload_instagram")
async def upload_instagram(
    video_filename: str = Form(...),
    caption: str = Form(""),
    auto_caption: bool = Form(False),
):
    """Upload a video to Instagram as a Reel."""
    from utils import OUTPUTS_DIR

    # Resolve the video file
    video_path = OUTPUTS_DIR / video_filename
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"Video file not found: {video_filename}")

    # Auto-generate caption if requested and no caption provided
    final_caption = caption.strip()
    if auto_caption and not final_caption:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if api_key and api_key != "your_openrouter_key_here":
            try:
                prompt = f"You are a social media expert. Write a short, engaging viral caption for a short-form video (TikTok/Reel) based on this video title. Only provide the caption and a few relevant hashtags. Do not include extra conversational text.\n\nTitle: {video_filename.replace('.mp4', '').replace('_', ' ')}"
                final_caption = openrouter_chat_completion(
                    api_key=api_key,
                    messages=[{"role": "user", "content": prompt}],
                    models=get_openrouter_models("OPENROUTER_CAPTION_MODELS", DEFAULT_CAPTION_MODELS),
                    timeout=15,
                )
                print(f"✨ Auto-generated caption: {final_caption[:80]}...")
            except Exception as e:
                print(f"⚠️ Caption auto-generation failed: {e}")
                final_caption = f"🔥 {video_filename.replace('.mp4', '').replace('_', ' ')} #reddit #storytime #viral"
        else:
            final_caption = f"🔥 {video_filename.replace('.mp4', '').replace('_', ' ')} #reddit #storytime #viral"

    try:
        print(f"📤 Starting Instagram upload: {video_filename}")
        cl = get_ig_client()

        # Upload as Reel
        media = await asyncio.to_thread(
            cl.clip_upload,
            str(video_path),
            final_caption
        )

        print(f"✅ Uploaded to Instagram! Media ID: {media.pk}")
        return {
            "status": "success",
            "media_id": str(media.pk),
            "caption_used": final_caption
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Instagram upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def run_pipeline_wrapper(
    job_id: str,
    text: str,
    title: str = "reddit_reel",
    voice: str = "en-US-ChristopherNeural",
    style_config: dict = None,
    max_duration: int = 60,
    video_bitrate: str = "15000k",
    tts_rate: str = "+10%",
    video_speed: float = 1.0,
    bg_video: str | None = None,
    bg_music: str | None = None,
    subreddit: str = "AskReddit",
    username: str = "u/user",
    score: int = 0,
    num_comments: int = 0,
    post_age: str = "2d",
):
    """Wrapper to call run_pipeline in a background thread without blocking."""
    print("🚀 Background task started for video generation.")
    try:
        run_pipeline(
            text=text,
            title=title,
            voice=voice,
            style_config=style_config,
            max_duration=max_duration,
            video_bitrate=video_bitrate,
            tts_rate=tts_rate,
            video_speed=video_speed,
            bg_video=bg_video,
            bg_music=bg_music,
            subreddit=subreddit,
            username=username,
            score=score,
            num_comments=num_comments,
            post_age=post_age,
        )
        print("✅ Background task completed.")
    except Exception as e:
        print(f"❌ Pipeline failed: {str(e)}")


def run_tracked_pipeline(
    job_id: str,
    text: str,
    title: str = "reddit_reel",
    voice: str = "en-US-ChristopherNeural",
    style_config: dict = None,
    max_duration: int = 60,
    video_bitrate: str = "15000k",
    tts_rate: str = "+10%",
    video_speed: float = 1.0,
    bg_video: str | None = None,
    bg_music: str | None = None,
    subreddit: str = "AskReddit",
    username: str = "u/user",
    score: int = 0,
    num_comments: int = 0,
    post_age: str = "2d",
):
    """Tracks pipeline state so the UI can poll for live output."""
    if PIPELINE_STATUS["job_id"] == job_id:
        PIPELINE_STATUS["state"] = "running"
        PIPELINE_STATUS["error"] = None

    print("Background task started for video generation.")
    try:
        run_pipeline(
            text=text,
            title=title,
            voice=voice,
            style_config=style_config,
            max_duration=max_duration,
            video_bitrate=video_bitrate,
            tts_rate=tts_rate,
            video_speed=video_speed,
            bg_video=bg_video,
            bg_music=bg_music,
            subreddit=subreddit,
            username=username,
            score=score,
            num_comments=num_comments,
            post_age=post_age,
        )
        if PIPELINE_STATUS["job_id"] == job_id:
            PIPELINE_STATUS["state"] = "completed"
            PIPELINE_STATUS["error"] = None
        print("Background task completed.")
    except Exception as e:
        if PIPELINE_STATUS["job_id"] == job_id:
            PIPELINE_STATUS["state"] = "failed"
            PIPELINE_STATUS["error"] = str(e)
        print(f"Pipeline failed: {str(e)}")


if __name__ == "__main__":
    print("Starting Reel Maker Web UI on http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

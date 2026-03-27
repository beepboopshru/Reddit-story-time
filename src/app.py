import asyncio
import os
import base64
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
from scraper import RedditScraper
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

app = FastAPI(title="Reel Maker Studio")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    """Generates an AI caption using OpenRouter (stepfun/step-3.5-flash:free)."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or api_key == "your_openrouter_key_here":
        raise HTTPException(status_code=400, detail="Missing OpenRouter API Key in .env file.")
        
    prompt = f"You are a social media expert. Write a short, engaging viral caption for a short-form video (TikTok/Reel) based on the following story. Only provide the caption and a few relevant hashtags. Do not include extra conversational text.\n\nStory: {text[:2000]}"
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "stepfun/step-3.5-flash:free",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        caption = data["choices"][0]["message"]["content"].strip()
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
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "google/gemini-2.0-flash-lite-preview-02-05:free",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }]
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        extracted = data["choices"][0]["message"]["content"].strip()

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



@app.post("/api/fetch-reddit-post")
async def fetch_reddit_post(url: str = Form(...)):
    """Fetches a Reddit post's content by URL using PRAW."""
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Please enter a Reddit URL.")

    if "reddit.com" not in url and "redd.it" not in url:
        raise HTTPException(status_code=400, detail="That doesn't look like a Reddit URL. Please paste a full reddit.com link.")

    try:
        scraper = RedditScraper()
        story, author = scraper.fetch_post_by_url(url)
        return {
            "title": story.title,
            "body": story.body,
            "author": author,
            "subreddit": story.subreddit,
            "score": story.score,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"Fetch Reddit Post Error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


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
    video_bitrate: str = Form("15000k"),
    tts_rate: str = Form("+10%"),
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
        run_pipeline_wrapper,
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

    return {"status": "processing initiated"}


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


def run_pipeline_wrapper(
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


if __name__ == "__main__":
    print("Starting Reel Maker Web UI on http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

"""
utils.py — Shared helpers for the Reel Maker pipeline.
Handles text cleaning, path management, and config loading.
"""

import os
import re
import random
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Paths ────────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
BG_VIDEOS_DIR = ASSETS_DIR / "background_videos"
BG_MUSIC_DIR = ASSETS_DIR / "bg_music"
OUTPUTS_DIR = ASSETS_DIR / "outputs"
TEMP_DIR = ROOT_DIR / "temp"

# Ensure directories exist
for d in [BG_VIDEOS_DIR, BG_MUSIC_DIR, OUTPUTS_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─── Config ───────────────────────────────────────────────────────────────────

def get_env(key: str, default: str = "") -> str:
    """Get an environment variable or return a default."""
    return os.getenv(key, default)


def get_output_resolution() -> tuple[int, int]:
    """Parse OUTPUT_RESOLUTION from env (e.g., '1080x1920') into (width, height)."""
    res = get_env("OUTPUT_RESOLUTION", "1080x1920")
    w, h = res.lower().split("x")
    return int(w), int(h)


# ─── Text Cleaning ───────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Sanitize Reddit post text for TTS consumption.
    Removes markdown artifacts, URLs, excessive whitespace.
    """
    # Remove markdown links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove plain URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove Reddit-specific markers
    text = re.sub(r'(?i)\b(edit|update|tldr|tl;dr)\s*:?', '', text)
    # Remove markdown bold/italic
    text = re.sub(r'[*_]{1,3}', '', text)
    # Remove blockquotes
    text = re.sub(r'^>+\s?', '', text, flags=re.MULTILINE)
    # Collapse multiple newlines into a single space
    text = re.sub(r'\n+', ' ', text)
    # Collapse excessive whitespace
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 3000) -> str:
    """
    Truncate text to a maximum character count, cutting at the last
    full sentence boundary to avoid choppy endings.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Find the last sentence-ending punctuation
    last_period = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_period > max_chars * 0.5:
        return truncated[:last_period + 1]
    return truncated


# ─── Asset Selection ─────────────────────────────────────────────────────────

def pick_random_background_video() -> Path:
    """Select a random video file from the background_videos directory."""
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    videos = [f for f in BG_VIDEOS_DIR.iterdir() if f.suffix.lower() in video_exts]
    if not videos:
        raise FileNotFoundError(
            f"No background videos found in {BG_VIDEOS_DIR}. "
            "Add .mp4 files (e.g., Minecraft parkour clips) to the folder."
        )
    return random.choice(videos)


def pick_random_bg_music() -> Path | None:
    """Select a random audio file from the bg_music directory, or None."""
    audio_exts = {'.mp3', '.wav', '.ogg', '.m4a'}
    tracks = [f for f in BG_MUSIC_DIR.iterdir() if f.suffix.lower() in audio_exts]
    if not tracks:
        return None
    return random.choice(tracks)


def generate_output_filename(title: str) -> Path:
    """Generate a safe, unique output filename from a post title."""
    # Check if the title ends with a part suffix (e.g., "_Part1", "_Part2")
    match = re.search(r'(_Part\d+)$', title)
    
    if match:
        suffix = match.group(1)
        base_title = title[:-len(suffix)]
        # Truncate base title so that base + suffix <= 50 chars
        safe_base = re.sub(r'[^\w\s-]', '', base_title)[:50 - len(suffix)].strip().replace(' ', '_')
        safe = f"{safe_base}{suffix}"
    else:
        safe = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '_')
        
    return OUTPUTS_DIR / f"{safe}.mp4"

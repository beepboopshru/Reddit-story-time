"""
main.py — Entry point for the Automated Reel Maker pipeline.

Usage:
    python main.py                     # Scrape + generate a reel
    python main.py --text "Custom text"  # Generate from custom text
    python main.py --skip-scrape       # Use last cached story
"""

import argparse
from pathlib import Path

from scraper import RedditScraper
from tts import TTSEngine
from transcription import Transcriber
from processor import VideoProcessor, get_media_duration
from reddit_card import RedditCardRenderer
from utils import TEMP_DIR, OUTPUTS_DIR, BG_VIDEOS_DIR, BG_MUSIC_DIR, pick_random_background_video, pick_random_bg_music


def run_pipeline(
    text: str | None = None,
    title: str = "reddit_reel",
    skip_scrape: bool = False,
    voice: str | None = None,
    style_config: dict | None = None,
    max_duration: int | None = None,
    video_bitrate: str | None = None,
    tts_rate: str | None = None,
    video_speed: float = 1.0,
    bg_video: str | None = None,
    bg_music: str | None = None,
    # Reddit post metadata (for intro card on Part 1)
    subreddit: str = "AskReddit",
    username: str = "u/user",
    score: int = 0,
    num_comments: int = 0,
    post_age: str = "2d",
):
    """
    Execute the full reel-making pipeline:
      1. Scrape (or use provided text)
      2. TTS → audio
      3. Transcribe → word timestamps
      4. Compose → final video
    """

    # ── Step 1: Get the story text ────────────────────────────────────────
    if text:
        story_text = text
        print(f"📝 Using custom text ({len(story_text)} chars)")
    elif skip_scrape:
        cached = TEMP_DIR / "last_story.txt"
        if not cached.exists():
            raise FileNotFoundError("No cached story found. Run without --skip-scrape first.")
        story_text = cached.read_text(encoding="utf-8")
        title = TEMP_DIR / "last_title.txt"
        title = title.read_text(encoding="utf-8") if title.exists() else "cached_reel"
        print(f"📝 Loaded cached story ({len(story_text)} chars)")
    else:
        print("🔍 Scraping Reddit for stories...")
        scraper = RedditScraper()
        stories = scraper.fetch_stories(limit=1)
        if not stories:
            raise RuntimeError("No suitable stories found. Try different subreddits or sort method.")

        story = stories[0]
        story_text = story.body  # body only — title is spoken separately as intro
        title = story.title
        subreddit = story.subreddit
        username = f"u/user"
        score = story.score
        print(f"📰 Selected: [{story.subreddit}] {story.title} ({story.score}↑)")

        # Cache for reuse
        (TEMP_DIR / "last_story.txt").write_text(story_text, encoding="utf-8")
        (TEMP_DIR / "last_title.txt").write_text(title, encoding="utf-8")

    # ── Step 2: Text-to-Speech ────────────────────────────────────────────
    print("\n🎙️  Generating TTS audio...")
    # Map shortcuts to full voice names
    voice_map = {
        "male": "en-US-ChristopherNeural",
        "female": "en-US-AvaNeural"
    }
    selected_voice = voice_map.get(voice.lower(), voice) if voice else None

    tts = TTSEngine(voice=selected_voice, rate=tts_rate)
    tts_audio = tts.generate(story_text, "tts_voice.mp3")

    # ── Step 2b: Generate title TTS (for intro card on Part 1) ───────────
    print("\n🎙️  Generating title TTS for intro...")
    title_audio = tts.generate(title, "tts_title.mp3")
    title_audio_dur = get_media_duration(title_audio)
    print(f"   Title audio: {title_audio_dur:.1f}s")

    # ── Step 2c: Render Reddit card ───────────────────────────────────────
    print("\n🖼️  Rendering Reddit intro card...")
    card_renderer = RedditCardRenderer(
        title=title,
        subreddit=subreddit,
        username=username,
        score=score,
        num_comments=num_comments,
        age=post_age,
    )
    intro_card_path = card_renderer.render()

    # ── Step 3: Transcribe for word timestamps ────────────────────────────
    print("\n🔤 Transcribing audio for subtitles...")
    transcriber = Transcriber()
    transcription = transcriber.transcribe(tts_audio)
    print(f"   Found {len(transcription.words)} words over {transcription.duration:.1f}s")

    # ── Step 4: Pick Assets ──────────────────────────────────────────────────
    print("\n🎬 Picking background assets...")
    # Pick Background Video
    if bg_video:
        background_video_path = BG_VIDEOS_DIR / bg_video
        if not background_video_path.exists():
            print(f"   ⚠️ Specified bg_video not found: {bg_video}. Falling back to random.")
            background_video_path = pick_random_background_video()
    else:
        background_video_path = pick_random_background_video()
    print(f"   📹 Background video: {background_video_path.name}")

    # Pick Background Music
    if bg_music:
        if bg_music.lower() == "none":
            background_music_path = None
            print("   🎵 Background music: [NONE]")
        else:
            background_music_path = BG_MUSIC_DIR / bg_music
            if not background_music_path.exists():
                print(f"   ⚠️ Specified bg_music not found: {bg_music}. Falling back to random.")
                background_music_path = pick_random_bg_music()
            else:
                 print(f"   🎵 Background music: {background_music_path.name}")
    else:
        background_music_path = pick_random_bg_music()
        if background_music_path:
            print(f"   🎵 Background music: {background_music_path.name}")

    # ── Step 5: Compose the video ─────────────────────────────────────────
    print("\n🎬 Composing final video(s)...")
    composer = VideoProcessor(max_duration=max_duration)
    
    # Use the selected background video path
    bg_path = background_video_path
    
    max_duration = composer.max_duration
    total_duration = transcription.duration
    
    # ── Identify Sentence Boundaries ──
    boundaries = []
    for i, w in enumerate(transcription.words):
        # A simple check for punctuation at the end of the word
        if any(w.word.endswith(p) for p in ['.', '?', '!']):
            boundaries.append(i)
            
    parts = []
    start_time = 0.0
    part_num = 1
    
    while start_time < total_duration:
        end_time_target = start_time + max_duration
        
        if end_time_target >= total_duration:
            # Last part
            end_time = total_duration
            next_start_time = total_duration
            follow_text = None
            follow_audio_path = None
        else:
            # Slicing logic: find the last sentence boundary before end_time_target
            valid_boundaries = [
                b for b in boundaries 
                if transcription.words[b].end <= end_time_target and transcription.words[b].end > start_time
            ]
            
            if not valid_boundaries:
                # Fallback if no punctuation found in this chunk
                end_time = end_time_target
                next_start_time = end_time
            else:
                last_boundary_idx = valid_boundaries[-1]
                end_time = transcription.words[last_boundary_idx].end
                
                # To make the consecutive part start with the last sentence
                # of the *previous* part, we find the sentence boundary BEFORE last_boundary_idx
                prev_boundaries = [b for b in boundaries if b < last_boundary_idx]
                if not prev_boundaries:
                    next_start_time = 0.0 # This was the first sentence
                else:
                    prev_boundary_idx = prev_boundaries[-1]
                    next_start_time = transcription.words[prev_boundary_idx + 1].start
                    
            # Prevent infinite loops in edge cases
            if next_start_time <= start_time:
                next_start_time = end_time
                
            follow_text = f"Follow for Part {part_num + 1}"
            follow_audio_path = tts.generate(follow_text, f"follow_part_{part_num+1}.mp3")
             
        # Generate custom output name for parts
        part_title = title if total_duration <= max_duration else f"{title}_Part{part_num}"
        
        # Only Part 1 gets the intro card
        is_first_part = (part_num == 1)
        output = composer.compose(
            tts_audio_path=tts_audio,
            transcription=transcription,
            title=part_title,
            bg_video_path=bg_path,
            start_time=start_time,
            end_time=end_time,
            follow_text=follow_text,
            follow_audio_path=follow_audio_path,
            style_config=style_config,
            video_bitrate=video_bitrate,
            video_speed=video_speed,
            intro_audio_path=title_audio if is_first_part else None,
            intro_card_path=intro_card_path if is_first_part else None,
            bg_music_path=background_music_path,
        )
        parts.append(output)
        
        start_time = next_start_time
        part_num += 1

    print(f"\n🎉 Done! Generated {len(parts)} reel(s):")
    for p in parts:
        print(f"   📂 {p}")
        
    return parts


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🎬 Automated Reel Maker — Reddit stories → short-form video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Scrape Reddit + generate reel
  python main.py --text "Hello world"     # Use custom text
  python main.py --skip-scrape            # Reuse last scraped story
  python main.py --bg-video clip.mp4      # Use specific background video
        """,
    )
    parser.add_argument("--text", type=str, help="Custom text to use instead of scraping")
    parser.add_argument("--skip-scrape", action="store_true", help="Use last cached story")
    parser.add_argument("--bg-video", type=str, help="Path to a specific background video")
    parser.add_argument("--title", type=str, default="reddit_reel", help="Video title")
    parser.add_argument("--voice", type=str, help="TTS voice name or 'male'/'female' shortcut")

    args = parser.parse_args()

    run_pipeline(
        text=args.text,
        title=args.title,
        skip_scrape=args.skip_scrape,
        bg_video=args.bg_video,
        voice=args.voice,
    )


if __name__ == "__main__":
    main()

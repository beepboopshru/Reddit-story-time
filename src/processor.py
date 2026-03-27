"""
processor.py — Video composition engine using FFmpeg.
Assembles TTS audio, background video, karaoke subtitles, and background music
into a final short-form vertical video using a heavily optimized FFmpeg subprocess.
"""

import os
import random
import subprocess
import re
import imageio_ffmpeg
from pathlib import Path

from transcription import TranscriptionResult, WordTimestamp
from utils import (
    get_env,
    get_output_resolution,
    pick_random_background_video,
    pick_random_bg_music,
    generate_output_filename,
    TEMP_DIR,
)


def get_media_duration(file_path: Path) -> float:
    """Extract media duration using ffmpeg instead of ffprobe."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-i", str(file_path)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if match:
        h, m, s = match.groups()
        return float(h) * 3600 + float(m) * 60 + float(s)
    return 0.0

class VideoProcessor:
    """
    Composes the final reel from individual assets using direct FFmpeg.
    """

    def __init__(self, max_duration: int | None = None):
        self.width, self.height = get_output_resolution()
        self.bg_music_volume = float(get_env("BG_MUSIC_VOLUME", "0.08"))
        self.max_duration = max_duration if max_duration is not None else int(get_env("MAX_DURATION_SECONDS", "60"))

    def compose(
        self,
        tts_audio_path: Path,
        transcription: TranscriptionResult,
        title: str = "reel",
        bg_video_path: Path | None = None,
        output_path: Path | None = None,
        start_time: float = 0.0,
        end_time: float | None = None,
        follow_text: str | None = None,
        follow_audio_path: Path | None = None,
        style_config: dict | None = None,
        video_bitrate: str | None = None,
        video_speed: float = 1.0,
        intro_audio_path: Path | None = None,
        intro_card_path: Path | None = None,
        bg_music_path: Path | None = None,
    ) -> Path:
        """Assemble the final video via FFmpeg native commands."""
        if end_time is None:
            end_time = transcription.duration

        if end_time == transcription.duration:
            end_time = min(end_time, start_time + self.max_duration)

        duration = end_time - start_time

        # ── Intro phase setup ──────────────────────────────────────────────────
        intro_duration = 0.0
        if intro_audio_path and intro_audio_path.exists():
            intro_duration = get_media_duration(intro_audio_path)

        total_duration = intro_duration + duration
        print(
            f"🎬 Composing FFmpeg video chunk ({start_time:.1f}s → {end_time:.1f}s) — {duration:.1f}s"
            + (f"  [+ {intro_duration:.1f}s intro card]" if intro_duration else "")
        )

        if output_path is None:
            output_path = generate_output_filename(title)

        # ── 1. Background Video ────────────────────────────────────────────────
        if bg_video_path is None:
            bg_video_path = pick_random_background_video()

        try:
            bg_dur = get_media_duration(bg_video_path)
            bg_start = random.uniform(0, max(0, bg_dur - 1))
        except Exception:
            bg_start = 0.0

        # ── 2. Build Subtitle File ─────────────────────────────────────────────
        ass_file = TEMP_DIR / f"subs_{title[:10].replace(' ', '_')}_{start_time:.0f}.ass"
        transcription.to_ass(
            ass_file, start_time, end_time, follow_text, style_config,
            intro_duration=intro_duration
        )
        ass_rel = os.path.relpath(ass_file, os.getcwd()).replace("\\", "/")

        # ── 3. Build FFmpeg Input List ─────────────────────────────────────────
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [ffmpeg_exe, "-y"]

        # Input 0: BG Video (looping)
        cmd.extend(["-stream_loop", "-1", "-ss", f"{bg_start:.2f}", "-i", str(bg_video_path)])
        input_idx = 1

        # Input 1 (optional): Intro TTS audio
        intro_audio_idx = -1
        if intro_audio_path and intro_duration > 0:
            cmd.extend(["-i", str(intro_audio_path)])
            intro_audio_idx = input_idx
            input_idx += 1

        # Input N: Body TTS audio
        body_audio_idx = input_idx
        cmd.extend(["-ss", str(start_time), "-t", str(duration), "-i", str(tts_audio_path)])
        input_idx += 1

        # Input N+1 (optional): BG Music
        bg_music_path = pick_random_bg_music()
        bg_music_idx = -1
        if bg_music_path:
            try:
                m_dur = get_media_duration(bg_music_path)
                m_start = random.uniform(0, max(0, m_dur - 1))
            except Exception:
                m_start = 0.0
            cmd.extend(["-stream_loop", "-1", "-ss", f"{m_start:.2f}", "-i", str(bg_music_path)])
            bg_music_idx = input_idx
            input_idx += 1

        # Input N+2 (optional): Follow audio
        follow_idx = -1
        if follow_audio_path:
            cmd.extend(["-i", str(follow_audio_path)])
            follow_idx = input_idx
            input_idx += 1

        # Input N+3 (optional): Reddit card PNG (looped for intro duration)
        card_idx = -1
        if intro_card_path and intro_card_path.exists() and intro_duration > 0:
            cmd.extend(["-loop", "1", "-t", f"{intro_duration + 0.5:.2f}", "-i", str(intro_card_path)])
            card_idx = input_idx
            input_idx += 1

        # ── 4. Build Filter Graph ──────────────────────────────────────────────
        video_filters = []
        audio_filters = []
        amix_streams = []

        # ── Video chain ────────────────────────────────────────────────────────
        # Apply playback speed manipulation (setpts)
        pts_modifier = 1.0 / video_speed
        scale_crop = (
            f"setpts={pts_modifier:.3f}*PTS,"
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height}:(iw-{self.width})/2:(ih-{self.height})/2,"
            f"setsar=1"
        )

        if card_idx >= 0:
            # Scale the card to ~90% of the video width
            card_w = int(self.width * 0.90)
            video_filters.append(f"[0:v]{scale_crop}[_bg]")
            video_filters.append(f"[{card_idx}:v]scale={card_w}:-1[_card]")
            # Overlay card centered horizontally, at 40% vertically, during intro
            video_filters.append(
                f"[_bg][_card]overlay="
                f"(W-w)/2:(H-h)*0.38:enable='lte(t,{intro_duration:.3f})'[_bgcard]"
            )
            video_filters.append(f"[_bgcard]ass='{ass_rel}'[v]")
        else:
            video_filters.append(f"[0:v]{scale_crop},ass='{ass_rel}'[v]")

        # ── Audio chain ────────────────────────────────────────────────────────
        if intro_audio_idx >= 0:
            audio_filters.append(f"[{intro_audio_idx}:a]volume=1.0[_intro]")
            audio_filters.append(f"[{body_audio_idx}:a]volume=1.0[_body]")
            audio_filters.append("[_intro][_body]concat=n=2:v=0:a=1[tts]")
        else:
            audio_filters.append(f"[{body_audio_idx}:a]volume=1.0[tts]")

        amix_streams.append("[tts]")

        if bg_music_idx >= 0:
            audio_filters.append(f"[{bg_music_idx}:a]volume={self.bg_music_volume}[_bgm]")
            amix_streams.append("[_bgm]")

        if follow_idx >= 0:
            delay_ms = int(max(0, total_duration - 1.5) * 1000)
            audio_filters.append(
                f"[{follow_idx}:a]adelay={delay_ms}|{delay_ms},volume=1.0[_follow]"
            )
            amix_streams.append("[_follow]")

        audio_filters.append(
            "".join(amix_streams)
            + f"amix=inputs={len(amix_streams)}:duration=first:dropout_transition=0[a]"
        )

        filter_complex = ";".join(video_filters + audio_filters)
        cmd.extend(["-filter_complex", filter_complex])

        # ── 5. Output Options ──────────────────────────────────────────────────
        codec = get_env("VIDEO_CODEC", "libx264")
        bitrate = video_bitrate if video_bitrate else get_env("VIDEO_BITRATE", "15000k")
        preset = "fast" if "nvenc" in codec else "ultrafast"

        cmd.extend([
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", codec,
            "-b:v", bitrate,
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(total_duration),
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            str(output_path)
        ])

        print(f"  → Running native FFmpeg Command ({codec})...")

        # Redirect to a file to avoid pipe buffer issues on Windows
        with open("ffmpeg_last_run.log", "w", encoding="utf-8") as f_log:
            result = subprocess.run(cmd, stdout=f_log, stderr=f_log, text=True)
            
        if result.returncode != 0:
            print(f"❌ FFmpeg failed with code {result.returncode}. Check ffmpeg_last_run.log for details.")
            raise RuntimeError(f"FFmpeg failed with code {result.returncode}")

        print(f"✅ Video saved → {output_path}  ({output_path.stat().st_size / (1024*1024):.1f} MB)")
        return output_path



if __name__ == "__main__":
    import sys
    print("Run `python main.py` instead.")
    sys.exit(1)

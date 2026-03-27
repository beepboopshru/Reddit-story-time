import subprocess
import random
import os
import tempfile
from pathlib import Path
from utils import get_output_resolution
import imageio_ffmpeg

class ThumbnailProcessor:
    def __init__(self):
        self.width, self.height = get_output_resolution()
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        # imageio_ffmpeg usually bundles ffprobe next to ffmpeg, or we can use ffmpeg itself to deduce length
        # but to be safe we'll use ffmpeg to get duration:
        # ffmpeg -i file.mp4 2>&1 | grep Duration

    def get_video_duration(self, video_path: Path) -> float:
        """Uses the bundled ffmpeg exe to extract duration of a video file."""
        cmd = [
            self.ffmpeg_exe,
            "-i", str(video_path)
        ]
        try:
            # Note: ffmpeg info prints to stderr
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = result.stderr
            # Look for: Duration: 00:05:43.08, start: 0.000000, bitrate: 1475 kb/s
            import re
            match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", output)
            if match:
                hours, minutes, seconds = match.groups()
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            return 60.0 # Fallback
        except Exception as e:
            print(f"Error getting duration for {video_path}: {e}")
            return 60.0 # Fallback to 60s

    def wrap_text(self, text: str, max_chars_per_line: int = 20) -> str:
        """Wraps text into multiple lines to prevent horizontal clipping in 1080p."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) <= max_chars_per_line:
                current_line.append(word)
                current_length += len(word) + 1 # +1 for space
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word) + 1
                
        if current_line:
            lines.append(" ".join(current_line))
            
            
            
        # Join with actual newlines
        return "\n".join(lines)

    def generate(self, bg_video_path: Path, text: str, style_config: dict, output_path: Path) -> Path:
        """Generates a highly-stylized thumbnail screenshot via FFmpeg."""
        
        # 1. Grab a highly random timestamp from the video
        duration = self.get_video_duration(bg_video_path)
        # Avoid the very first or very last seconds for better imagery
        safe_start = min(5.0, duration * 0.1)
        safe_end = max(safe_start, duration - 5.0)
        random_timestamp = random.uniform(safe_start, safe_end)

        # 2. Extract style attributes
        font_color = style_config.get("color", "#FFFFFF")
        stroke_color = style_config.get("stroke_color", "#000000")
        stroke_width = style_config.get("stroke_width", 4)
        
        # Convert hex colors (#FFD700) to standard FFmpeg format (0xFFD700)
        fc = font_color.replace("#", "0x")
        sc = stroke_color.replace("#", "0x")
        
        # 3. Prepare word-wrapped text and save to temp file
        wrapped_text = self.wrap_text(text, max_chars_per_line=15)
        
        # We use a temp file for text to avoid shell escaping issues with multi-line strings
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tf:
            tf.write(wrapped_text)
            temp_text_path = tf.name

        try:
            # We use a massive box of drop shadows for a "clickable" Youtube/TikTok look
            # We must escape the backslashes in the path for FFmpeg on Windows
            safe_text_path = temp_text_path.replace("\\", "/").replace(":", "\\:")
            
            filter_complex = (
                f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height}:(iw-{self.width})/2:(ih-{self.height})/2,"
                # We add a 40% black overlay to make the text pop dramatically
                "colorchannelmixer=rr=0.6:gg=0.6:bb=0.6,"
                # drawtext filter for the main title
                f"drawtext=textfile='{safe_text_path}':"
                "font=Impact:fontsize=110:line_spacing=15:"
                f"fontcolor={fc}:"
                f"bordercolor={sc}:borderw={stroke_width}:"
                "shadowcolor=black@0.9:shadowx=8:shadowy=8:"
                "x=(w-text_w)/2:y=(h-text_h)/2[out]"
            )

            cmd = [
                self.ffmpeg_exe, "-y",
                "-ss", f"{random_timestamp:.2f}",
                "-i", str(bg_video_path),
                "-vframes", "1",
                "-filter_complex", filter_complex,
                "-map", "[out]",
                "-q:v", "2", 
                str(output_path)
            ]

            print(f"Generating Thumbnail at timestamp {random_timestamp:.2f}s...")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return output_path
        finally:
            # Clean up temp file
            if os.path.exists(temp_text_path):
                os.remove(temp_text_path)

"""
transcription.py — Word-level transcription using Faster-Whisper.
Generates precise timestamps for karaoke-style subtitles.
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from faster_whisper import WhisperModel
from utils import get_env, TEMP_DIR


@dataclass
class WordTimestamp:
    """A single word with its start and end time in seconds."""
    word: str
    start: float
    end: float


@dataclass
class TranscriptionResult:
    """Full transcription result with word-level timing."""
    words: list[WordTimestamp]
    full_text: str
    duration: float  # total audio duration in seconds

    def to_json(self, path: Path | None = None) -> str:
        """Serialize to JSON. Optionally save to file."""
        data = {
            "full_text": self.full_text,
            "duration": self.duration,
            "words": [asdict(w) for w in self.words],
        }
        json_str = json.dumps(data, indent=2)
        if path:
            path.write_text(json_str, encoding="utf-8")
        return json_str

    @classmethod
    def from_json(cls, path: Path) -> "TranscriptionResult":
        """Load a transcription result from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        words = [WordTimestamp(**w) for w in data["words"]]
        return cls(words=words, full_text=data["full_text"], duration=data["duration"])

    def to_ass(self, output_ass_path: Path, start_time: float, end_time: float, follow_text: str | None = None, style_config: dict | None = None, intro_duration: float = 0.0) -> Path:
        """
        Generate an .ass (Advanced SubStation Alpha) subtitle file for a specific time window.
        """
        def format_time(seconds: float) -> str:
            # ASS time format: H:MM:SS.cs (centiseconds)
            h = int(seconds / 3600)
            m = int((seconds % 3600) / 60)
            s = int(seconds % 60)
            cs = int((seconds - int(seconds)) * 100)
            return f"{h}:{m:02}:{s:02}.{cs:02}"
            
        def hex_to_ass_color(hex_str: str) -> str:
            """Convert #RRGGBB to ASS format: &H00BBGGRR"""
            hex_str = hex_str.lstrip('#')
            if len(hex_str) != 6:
                return "&H00FFFFFF" # Default white
            # ASS format is Blue Green Red
            r, g, b = hex_str[0:2], hex_str[2:4], hex_str[4:6]
            return f"&H00{b}{g}{r}"

        # Default styles if no config provided
        if not style_config:
            style_config = {
                "Highlight": {"font_size": 110, "color": "#FFD700", "stroke_color": "#000000", "stroke_width": 3},
                "Follow": {"font_size": 100, "color": "#00AAFF", "stroke_color": "#000000", "stroke_width": 3}
            }
            
        hl = style_config.get("Highlight", {})
        fl = style_config.get("Follow", {})
        
        hl_color = hex_to_ass_color(hl.get("color", "#FFD700"))
        hl_stroke = hex_to_ass_color(hl.get("stroke_color", "#000000"))
        hl_size = hl.get("font_size", 110)
        hl_sw = hl.get("stroke_width", 3)
        
        fl_color = hex_to_ass_color(fl.get("color", "#00AAFF"))
        fl_stroke = hex_to_ass_color(fl.get("stroke_color", "#000000"))
        fl_size = fl.get("font_size", 100)
        fl_sw = fl.get("stroke_width", 3)
        
        ass_content = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Highlight,Impact,{hl_size},{hl_color},&H000000FF,{hl_stroke},&H00000000,0,0,0,0,100,100,0,0,1,{hl_sw},0,5,0,0,0,1",
            f"Style: Follow,Impact,{fl_size},{fl_color},&H000000FF,{fl_stroke},&H00000000,0,0,0,0,100,100,0,0,1,{fl_sw},0,5,0,0,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        
        # Word subtitles — skip the intro window; shift body words by intro_duration
        intro_end_global = start_time + intro_duration  # global timestamp where intro ends
        for word_data in self.words:
            w_start_global = word_data.start
            w_end_global = word_data.end

            # Skip words outside this chunk
            if w_end_global <= start_time or w_start_global >= end_time:
                continue

            w_start_local = max(0.0, w_start_global - start_time) + intro_duration
            w_end_local   = min(end_time - start_time, w_end_global - start_time) + intro_duration

            if w_end_local <= w_start_local:
                continue

            start_str = format_time(w_start_local)
            end_str = format_time(w_end_local)
            display_text = word_data.word.upper()

            # Use \pos(X,Y) to place at 45% of screen height (540, 864)
            ass_content.append(
                f"Dialogue: 0,{start_str},{end_str},Highlight,,0,0,0,,{{\\pos(540,864)}}{display_text}"
            )

        # Follow text
        if follow_text:
            chunk_duration = end_time - start_time
            f_start = max(0.0, chunk_duration - 1.5)
            f_end = chunk_duration
            
            if f_end > f_start:
                ass_content.append(
                    f"Dialogue: 0,{format_time(f_start)},{format_time(f_end)},Follow,,0,0,0,,{{\\pos(540,864)}}{follow_text}"
                )
                
        output_ass_path.write_text("\n".join(ass_content), encoding="utf-8")
        return output_ass_path


class Transcriber:
    """
    Transcribe audio with word-level timestamps using Faster-Whisper.

    Usage:
        transcriber = Transcriber()
        result = transcriber.transcribe("path/to/audio.mp3")
        for w in result.words:
            print(f"{w.start:.2f}s → {w.end:.2f}s  '{w.word}'")
    """

    def __init__(self, model_size: str | None = None):
        self.model_size = model_size or get_env("WHISPER_MODEL", "base")
        print(f"🔄 Loading Whisper model '{self.model_size}'...")
        self.model = WhisperModel(
            self.model_size,
            device=get_env("DEVICE", "cpu"),
            compute_type="int8",
        )
        print("✅ Whisper model loaded.")

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        """
        Transcribe an audio file and extract word-level timestamps.

        Args:
            audio_path: Path to the audio file (.mp3, .wav, etc.)

        Returns:
            TranscriptionResult with per-word timing data.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        segments, info = self.model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language="en",
        )

        words: list[WordTimestamp] = []
        full_text_parts: list[str] = []

        from numerize import numerize
        
        for segment in segments:
            full_text_parts.append(segment.text)
            if segment.words:
                i = 0
                while i < len(segment.words):
                    word_info = segment.words[i]
                    word_text = word_info.word.strip()
                    
                    # Look ahead to see if we can form a number phrase
                    # e.g., "fifty" + "thousand" + "dollars"
                    phrase = word_text
                    end_idx = i
                    
                    # Try to add up to 4 more words to see if it makes a number
                    for j in range(1, 5):
                        if i + j < len(segment.words):
                            next_word = segment.words[i+j].word.strip()
                            test_phrase = phrase + " " + next_word
                            
                            try:
                                numerized = numerize.numerize(test_phrase)
                                # If numerize changed the string substantially (more than just adding $ signs)
                                # or if it successfully merged words, we keep looking
                                if numerized != test_phrase and not test_phrase.isdigit():
                                    phrase = test_phrase
                                    end_idx = i + j
                            except Exception:
                                # numerizer has bugs with certain string combinations. Ignore and continue.
                                pass
                                
                    
                    if end_idx > i:
                        # We found a multi-word number phrase
                        try:
                            final_word = numerize.numerize(phrase)
                            # Add dollar sign if the phrase contained 'dollars'
                            if "dollar" in phrase.lower() and not final_word.startswith("$"):
                                 final_word = "$" + final_word.replace("dollars", "").replace("dollar", "").strip()
                        except Exception:
                            final_word = phrase
                            
                        words.append(WordTimestamp(
                            word=final_word,
                            start=round(word_info.start, 3),
                            end=round(segment.words[end_idx].end, 3),
                        ))
                        i = end_idx + 1
                    else:
                        # Normal word
                        words.append(WordTimestamp(
                            word=word_text,
                            start=round(word_info.start, 3),
                            end=round(word_info.end, 3),
                        ))
                        i += 1

        result = TranscriptionResult(
            words=words,
            full_text=" ".join(full_text_parts).strip(),
            duration=round(info.duration, 3),
        )

        # Cache the result to disk
        cache_path = TEMP_DIR / f"{audio_path.stem}_transcript.json"
        result.to_json(cache_path)
        print(f"✅ Transcription complete → {len(words)} words, {info.duration:.1f}s")
        print(f"   Cached at {cache_path}")

        return result


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python transcription.py <audio_file>")
        sys.exit(1)

    t = Transcriber()
    result = t.transcribe(sys.argv[1])

    print(f"\n📝 Full text: {result.full_text[:200]}...")
    print(f"\n🕐 First 10 words with timestamps:")
    for w in result.words[:10]:
        print(f"  {w.start:6.2f}s → {w.end:6.2f}s  '{w.word}'")

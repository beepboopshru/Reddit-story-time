"""
tts.py — Text-to-Speech engine using Microsoft Edge-TTS.
Converts story text into natural-sounding audio files.
"""

import asyncio
import edge_tts
from pathlib import Path
from utils import get_env, TEMP_DIR


class TTSEngine:
    """
    Wraps edge-tts to generate high-quality neural TTS audio.

    Usage:
        engine = TTSEngine()
        audio_path = engine.generate("Hello world, this is a test.")
    """

    def __init__(self, voice: str | None = None, rate: str | None = None):
        self.voice = voice or get_env("TTS_VOICE", "en-US-ChristopherNeural")
        self.rate = rate or get_env("TTS_RATE", "+10%") # Increase speed by default by 10%

    async def _generate_async(self, text: str, output_path: Path) -> Path:
        """Internal async method to generate TTS audio via edge-tts."""
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await communicate.save(str(output_path))
        return output_path

    def generate(self, text: str, filename: str = "tts_output.mp3") -> Path:
        """
        Generate TTS audio from text.

        Args:
            text:     The story text to synthesize.
            filename: Output filename (saved in temp directory).

        Returns:
            Path to the generated .mp3 file.
        """
        output_path = TEMP_DIR / filename
        asyncio.run(self._generate_async(text, output_path))
        print(f"✅ TTS audio saved → {output_path}  ({output_path.stat().st_size / 1024:.0f} KB)")
        return output_path

    @staticmethod
    def list_voices(language_filter: str = "en") -> list[str]:
        """List available edge-tts voices filtered by language prefix."""

        async def _list():
            voices = await edge_tts.list_voices()
            return [
                f"{v['ShortName']}  ({v['Gender']})"
                for v in voices
                if v['Locale'].startswith(language_filter)
            ]

        return asyncio.run(_list())


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = TTSEngine()

    # List a few voices
    print("Available English voices:")
    for v in engine.list_voices()[:10]:
        print(f"  • {v}")

    # Generate a test clip
    test_text = (
        "Am I the jerk for refusing to share my lottery winnings with my family? "
        "So, I won fifty thousand dollars last month and decided to keep it private."
    )
    path = engine.generate(test_text, "test_tts.mp3")
    print(f"Test audio at: {path}")

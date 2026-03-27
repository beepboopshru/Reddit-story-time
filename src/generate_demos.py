import os
from pathlib import Path
from tts import TTSEngine

# We'll save demos into static/demos so they can be loaded instantly via URL
DEMOS_DIR = Path(__file__).parent / "static" / "demos"
DEMOS_DIR.mkdir(parents=True, exist_ok=True)

def generate_all_demos():
    engine = TTSEngine()
    
    # TTSEngine already has a synchronous list_voices wrapper
    raw_voices = engine.list_voices(language_filter="en")
    
    # The wrapper returns a formatted string: "en-US-ChristopherNeural  (Male)"
    # We just need to extract the short name ID
    voices = []
    for v in raw_voices:
        voices.append(v.split("  (")[0].strip())
        
    print(f"Generating demos for {len(voices)} voices...")
    
    for i, vid in enumerate(voices, 1):
        demo_path = DEMOS_DIR / f"{vid}.mp3"
        if not demo_path.exists():
            print(f"[{i}/{len(voices)}] Generating: {vid}")
            try:
                # generate is synchronous and wraps asyncio underneath
                e = TTSEngine(voice=vid)
                e.generate("Hi, this is a sample of my voice for your next reel.", str(demo_path))
            except Exception as ex:
                print(f"  -> Failed {vid}: {ex}")
        else:
            print(f"[{i}/{len(voices)}] Skipped {vid} (already exists)")
            
    print("All demos generated!")

if __name__ == "__main__":
    generate_all_demos()

"""
Stage 4: TTS Engine
Uses edge-tts (free, no API key, Microsoft neural voices). Unlike most free
TTS options, edge-tts streams WordBoundary events alongside the audio, so we
get precise per-word start/end timing for free -- no separate forced-alignment
pass (e.g. Whisper) is needed to sync captions to the voice.
"""
import asyncio
import json
import time
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "style.json").read_text())


async def _synthesize_once(text: str, out_audio: Path, out_timing: Path) -> list[dict]:
    voice_cfg = CONFIG["voice"]
        communicate = edge_tts.Communicate(
        text, voice_cfg["name"], rate=voice_cfg["rate"], pitch=voice_cfg["pitch"],
        boundary="WordBoundary",
    )

    word_boundaries = []
    out_audio.parent.mkdir(parents=True, exist_ok=True)

    with open(out_audio, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append(
                    {
                        "word": chunk["text"],
                        "start": chunk["offset"] / 1e7,  # 100-ns units -> seconds
                        "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                    }
                )

            out_timing.write_text(json.dumps(word_boundaries, indent=2))
    if text.strip() and not word_boundaries:
        raise RuntimeError(
            "edge-tts returned audio but zero word-timing events -- captions "
            "would be unsynced. This usually means the installed edge-tts "
            "version changed its metadata format again; check that "
            "Communicate(..., boundary='WordBoundary') is still honored."
        )
    return word_boundaries


async def synthesize(
    text: str, out_audio: Path, out_timing: Path,
    max_attempts: int = 4, base_delay: int = 20,
) -> list[dict]:
    for attempt in range(1, max_attempts + 1):
        try:
            return await _synthesize_once(text, out_audio, out_timing)
        except Exception as e:
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(f"edge-tts call failed ({type(e).__name__}: {e}). "
                  f"Retrying in {delay}s (attempt {attempt}/{max_attempts})...")
            if out_audio.exists():
                out_audio.unlink()  # don't leave a half-written file behind
            await asyncio.sleep(delay)


def generate_voiceover(script: dict, project_dir: Path) -> tuple[Path, list[dict]]:
    """Generates one continuous VO for the whole script and returns per-scene
    word timing by slicing the full word-boundary list at scene text boundaries."""
    full_text = " ".join(scene["text"] for scene in script["scenes"])
    audio_path = project_dir / "voiceover.wav"
    timing_path = project_dir / "word_timing.json"

    words = asyncio.run(synthesize(full_text, audio_path, timing_path))

    # Walk the flat word list and split it back into per-scene chunks by
    # matching word counts, so each scene knows its own start/end window.
    cursor = 0
    for scene in script["scenes"]:
        n_words = len(scene["text"].split())
        scene_words = words[cursor: cursor + n_words]
        scene["start"] = scene_words[0]["start"] if scene_words else 0.0
        scene["end"] = scene_words[-1]["end"] if scene_words else 0.0
        scene["word_timing"] = scene_words
        cursor += n_words

    (project_dir / "script.json").write_text(json.dumps(script, indent=2))
    return audio_path, words


if __name__ == "__main__":
    import sys

    project_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest"
    script = json.loads((project_dir / "script.json").read_text())
    audio_path, words = generate_voiceover(script, project_dir)
    print(f"Voiceover: {audio_path}")
    print(f"Total words timed: {len(words)}")

"""
Stage 1: Visual Analyzer
Scans input/visuals for videos and images, builds a tagged database from
filenames (e.g. person_thinking_dark_room.mp4 -> tags: person, thinking,
dark, room). No AI tagging needed -- keyword tags are enough for the scene
matcher and cost nothing.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VISUALS_DIR = ROOT / "input" / "visuals"
DB_PATH = ROOT / "config" / "visuals_db.json"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _tags_from_filename(path: Path) -> list[str]:
    stem = path.stem.lower()
    parts = re_split(stem)
    return [p for p in parts if p and not p.isdigit()]


def re_split(text: str) -> list[str]:
    import re

    return re.split(r"[_\-\s]+", text)


def _duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def build_visuals_db() -> list[dict]:
    entries = []
    for path in sorted(VISUALS_DIR.rglob("*")):
        if path.suffix.lower() in VIDEO_EXTS:
            entries.append({
                "file": str(path.relative_to(ROOT)),
                "type": "video",
                "duration": _duration(path),
                "tags": _tags_from_filename(path),
            })
        elif path.suffix.lower() in IMAGE_EXTS:
            entries.append({
                "file": str(path.relative_to(ROOT)),
                "type": "image",
                "duration": None,
                "tags": _tags_from_filename(path),
            })

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_text(json.dumps(entries, indent=2))
    return entries


if __name__ == "__main__":
    db = build_visuals_db()
    print(f"Tagged {len(db)} visuals -> {DB_PATH}")
    if not db:
        print("WARNING: input/visuals is empty. Add clips/images before running the full pipeline.")

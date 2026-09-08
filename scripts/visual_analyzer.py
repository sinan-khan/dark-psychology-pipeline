"""
Stage 1: Visual Analyzer
Tags each clip/image by what's actually IN it, using Gemini's vision
capability -- not by filename. Filename-based tagging meant scene matching
was only as good as how carefully clips happened to be named; this fixes
that at the source.

Tags are cached per-file (keyed on size+mtime), so re-running only costs API
calls for clips that are new or have changed -- a stable library re-tags
nothing.
"""
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
VISUALS_DIR = ROOT / "input" / "visuals"
DB_PATH = ROOT / "config" / "visuals_db.json"
KEYFRAME_DIR = ROOT / "config" / ".keyframes"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
TAG_MODEL_FALLBACKS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"]

TAG_PROMPT = """Look at this image, a frame from a short b-roll clip for a
dark-psychology / manipulation-tactics narration video. Return ONLY a JSON
array of 4-8 short, lowercase, concrete tags describing what's visually
shown -- subjects, objects, setting, action, mood. No markdown, no
explanation. Example: ["hand", "chess board", "reaching", "strategy",
"dim lighting"]"""


def _file_signature(path: Path) -> str:
    stat = path.stat()
    return hashlib.md5(f"{path.name}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()


def _tags_from_filename(path: Path) -> list[str]:
    stem = path.stem.lower()
    parts = re.split(r"[_\-\s]+", stem)
    return [p for p in parts if p and not p.isdigit()]


def _extract_keyframe(video_path: Path, out_path: Path) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(out_path)],
            check=True, capture_output=True,
        )
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        return False


def _duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _tag_image(image_path: Path) -> list[str]:
    """Tries each fallback model in turn; returns [] if all fail (caller
    falls back to filename tags so a clip is never left completely untagged)."""
    image_bytes = image_path.read_bytes()
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime)

    for model in TAG_MODEL_FALLBACKS:
        for attempt in range(2):
            try:
                response = CLIENT.models.generate_content(
                    model=model, contents=[part, TAG_PROMPT],
                )
                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw[raw.find("["):]
                tags = json.loads(raw)
                return [str(t).lower() for t in tags]
            except (genai_errors.ServerError, genai_errors.ClientError) as e:
                code = getattr(e, "code", None)
                if code not in {429, 500, 502, 503, 504} or attempt == 1:
                    break
                time.sleep(15)
            except Exception:
                break
    return []


def build_visuals_db() -> list[dict]:
    existing = {}
    if DB_PATH.exists():
        for entry in json.loads(DB_PATH.read_text()):
            existing[entry["file"]] = entry

    KEYFRAME_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    newly_tagged = 0

    for path in sorted(VISUALS_DIR.rglob("*")):
        if path.suffix.lower() not in VIDEO_EXTS | IMAGE_EXTS:
            continue

        rel = str(path.relative_to(ROOT))
        sig = _file_signature(path)
        prior = existing.get(rel)
        if prior and prior.get("signature") == sig and prior.get("tags"):
            entries.append(prior)
            continue

        is_video = path.suffix.lower() in VIDEO_EXTS
        if is_video:
            keyframe_path = KEYFRAME_DIR / f"{path.stem}.jpg"
            tag_source = keyframe_path if _extract_keyframe(path, keyframe_path) else None
        else:
            tag_source = path

        tags = _tag_image(tag_source) if tag_source else []
        if not tags:
            tags = _tags_from_filename(path)
        else:
            newly_tagged += 1

        entries.append({
            "file": rel,
            "type": "video" if is_video else "image",
            "duration": _duration(path) if is_video else None,
            "tags": tags,
            "signature": sig,
        })

    DB_PATH.write_text(json.dumps(entries, indent=2))
    if newly_tagged:
        print(f"Vision-tagged {newly_tagged} new/changed clip(s); "
              f"{len(entries) - newly_tagged} reused cached tags.")
    return entries


if __name__ == "__main__":
    db = build_visuals_db()
    print(f"Tagged {len(db)} visuals -> {DB_PATH}")
    if not db:
        print("WARNING: input/visuals is empty. Add clips/images before running the full pipeline.")
    for entry in db:
        print(f"  {entry['file']:40s} {entry['tags']}")

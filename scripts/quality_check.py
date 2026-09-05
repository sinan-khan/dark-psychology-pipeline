"""
Stage 8: Quality Checker
Cheap ffprobe-based sanity checks on the final render. Not a substitute for
watching the video, but catches the failure modes that break automated runs:
wrong resolution, no audio track, near-zero duration, missing file.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "style.json").read_text())


def _probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def check(video_path: Path) -> list[str]:
    problems = []
    if not video_path.exists() or video_path.stat().st_size == 0:
        return [f"{video_path} is missing or empty -- render failed."]

    info = _probe(video_path)
    video_streams = [s for s in info["streams"] if s["codec_type"] == "video"]
    audio_streams = [s for s in info["streams"] if s["codec_type"] == "audio"]

    if not video_streams:
        problems.append("No video stream found.")
    else:
        v = video_streams[0]
        want_w, want_h = CONFIG["resolution"]
        if int(v["width"]) != want_w or int(v["height"]) != want_h:
            problems.append(f"Resolution is {v['width']}x{v['height']}, expected {want_w}x{want_h}.")

    if not audio_streams:
        problems.append("No audio stream found -- voiceover/music mix likely failed.")

    duration = float(info["format"].get("duration", 0))
    lo, hi = CONFIG["video"]["target_total_seconds"]
    if duration < lo - 5 or duration > hi + 15:
        problems.append(f"Duration is {duration:.1f}s, expected roughly {lo}-{hi}s.")

    return problems


if __name__ == "__main__":
    video_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest" / "final.mp4"
    problems = check(video_path)
    if problems:
        print("QUALITY CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("Quality check passed.")

"""
Stage 7: Video Compositor (FFmpeg)
Builds one normalized, silent video segment per scene (trimmed/looped video,
or a slow Ken Burns zoom for images), concatenates them, burns in the .ass
captions, then mixes the voiceover with a ducked background music bed.
"""
import json
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "style.json").read_text())
MUSIC_DIR = ROOT / "input" / "music"


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _build_segment(scene: dict, out_path: Path) -> None:
    width, height = CONFIG["resolution"]
    fps = CONFIG["fps"]
    duration = max(scene["end"] - scene["start"], CONFIG["video"]["min_scene_seconds"])
    src = ROOT / scene["visual_file"]

    scale_crop = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

    if scene["visual_type"] == "video":
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src),
            "-t", str(duration),
            "-vf", f"{scale_crop},fps={fps}",
            "-an", str(out_path),
        ]
    else:  # image -> slow Ken Burns zoom
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(src),
            "-t", str(duration),
            "-vf",
            f"{scale_crop},zoompan=z='min(zoom+0.0015,1.15)':d={int(duration*fps)}:s={width}x{height}:fps={fps}",
            "-an", str(out_path),
        ]
    _run(cmd)


def _pick_music() -> Path | None:
    tracks = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
    return random.choice(tracks) if tracks else None


def compose(project_dir: Path) -> Path:
    script = json.loads((project_dir / "script.json").read_text())
    segments_dir = project_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    concat_list = project_dir / "concat_list.txt"
    with open(concat_list, "w") as f:
        for i, scene in enumerate(script["scenes"]):
            seg_path = segments_dir / f"scene_{i:02d}.mp4"
            _build_segment(scene, seg_path)
            f.write(f"file '{seg_path.resolve()}'\n")

    silent_video = project_dir / "silent_video.mp4"
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(silent_video),
    ])

    captioned_video = project_dir / "captioned_video.mp4"
    ass_path = project_dir / "captions.ass"
    _run([
        "ffmpeg", "-y", "-i", str(silent_video),
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        str(captioned_video),
    ])

    voiceover = project_dir / "voiceover.wav"
    music = _pick_music()
    final_video = project_dir / "final.mp4"
    duck_db = CONFIG["music"]["duck_db"]
    voice_gain = CONFIG["music"]["voice_gain_db"]

    if music:
        _run([
            "ffmpeg", "-y", "-i", str(captioned_video), "-i", str(voiceover),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"[1:a]volume={voice_gain}dB[voice];"
            f"[2:a]volume={duck_db}dB[music];"
            f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(final_video),
        ])
    else:
        _run([
            "ffmpeg", "-y", "-i", str(captioned_video), "-i", str(voiceover),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(final_video),
        ])

    return final_video


if __name__ == "__main__":
    import sys

    project_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest"
    out = compose(project_dir)
    print(f"Final video: {out}")

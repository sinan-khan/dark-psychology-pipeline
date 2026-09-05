"""
Orchestrator: runs the full pipeline end to end.

    python main.py [project_name]

If project_name is omitted, uses a timestamp. Each run creates
projects/<name>/ containing every intermediate artifact plus the final video,
and copies the final video to output/<name>.mp4.
"""
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from topic_script_engine import generate_script
from tts_engine import generate_voiceover
from caption_engine import build_ass
from visual_analyzer import build_visuals_db
from scene_planner import plan_scenes
from compose import compose
from quality_check import check

ROOT = Path(__file__).resolve().parent.parent


def run(project_name: str | None = None) -> Path:
    project_name = project_name or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    project_dir = ROOT / "projects" / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    print("1/6 Analyzing visual library...")
    visuals = build_visuals_db()
    if not visuals:
        raise RuntimeError("input/visuals is empty. Add clips/images before running.")

    print("2/6 Generating topic + script...")
    script = generate_script()

    print("3/6 Generating voiceover + word timing...")
    generate_voiceover(script, project_dir)  # writes updated script.json with timing

    print("4/6 Planning scenes (matching visuals)...")
    import json
    script = json.loads((project_dir / "script.json").read_text())
    script = plan_scenes(script)
    (project_dir / "script.json").write_text(json.dumps(script, indent=2))

    print("5/6 Building captions + composing final video...")
    build_ass(script, project_dir / "captions.ass")
    final_video = compose(project_dir)

    print("6/6 Running quality check...")
    problems = check(final_video)
    if problems:
        print("QUALITY CHECK FAILED:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(1)

    output_path = ROOT / "output" / f"{project_name}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(final_video, output_path)

    print(f"\nDone: {output_path}")
    return output_path


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else None
    run(name)

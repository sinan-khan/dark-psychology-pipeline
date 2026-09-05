"""
Stage 3b: Scene Planner
Matches each script scene's visual_tags against the tagged visual database
using simple overlap scoring (free, no ML needed). Falls back to the
least-recently-used clip if nothing scores above zero, so no scene is ever
left without footage.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "config" / "visuals_db.json"


def _score(scene_tags: list[str], clip_tags: list[str]) -> int:
    return len(set(scene_tags) & set(clip_tags))


def plan_scenes(script: dict) -> dict:
    visuals = json.loads(DB_PATH.read_text())
    if not visuals:
        raise RuntimeError("visuals_db.json is empty -- run visual_analyzer.py first.")

    usage_count = {v["file"]: 0 for v in visuals}

    for scene in script["scenes"]:
        scored = sorted(
            visuals,
            key=lambda v: (-_score(scene.get("visual_tags", []), v["tags"]), usage_count[v["file"]]),
        )
        chosen = scored[0]
        scene["visual_file"] = chosen["file"]
        scene["visual_type"] = chosen["type"]
        usage_count[chosen["file"]] += 1

    return script


if __name__ == "__main__":
    import sys

    project_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest"
    script = json.loads((project_dir / "script.json").read_text())
    script = plan_scenes(script)
    (project_dir / "script.json").write_text(json.dumps(script, indent=2))
    for s in script["scenes"]:
        print(f"{s['text'][:50]:50s} -> {s['visual_file']}")

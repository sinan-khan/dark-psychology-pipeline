"""
Stage 6: Caption Engine
Builds an .ass subtitle file with per-word karaoke timing. Each scene's
'highlight' word (chosen by the Script Engine) renders in yellow; every other
word renders in white. FFmpeg burns this in directly via libass.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "style.json").read_text())

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{font_size},{main_color},{main_color},{outline_color},&H00000000,1,0,0,0,100,100,0,0,1,{outline_width},0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _clean(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def build_ass(script: dict, out_path: Path) -> Path:
    cap_cfg = CONFIG["caption"]
    width, height = CONFIG["resolution"]

    lines = [
        ASS_HEADER.format(
            width=width,
            height=height,
            font=cap_cfg["font"],
            font_size=cap_cfg["font_size"],
            main_color=cap_cfg["main_color"],
            outline_color=cap_cfg["outline_color"],
            outline_width=cap_cfg["outline_width"],
            margin_v=cap_cfg["margin_v"],
        )
    ]

    for scene in script["scenes"]:
        highlight_clean = _clean(scene.get("highlight", ""))
        words = scene.get("word_timing", [])

        # group into short phrases (2-4 words) so the screen doesn't show a
        # whole sentence at once -- matches the word-pop reel style
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            chunk = words[i: i + chunk_size]
            if not chunk:
                continue
            start, end = chunk[0]["start"], chunk[-1]["end"]

            rendered = []
            for w in chunk:
                colour = (
                    cap_cfg["highlight_color"]
                    if _clean(w["word"]) == highlight_clean and highlight_clean
                    else cap_cfg["main_color"]
                )
                rendered.append(f"{{\\c{colour}}}{w['word'].upper() if colour == cap_cfg['highlight_color'] else w['word']}")

            text = " ".join(rendered)
            lines.append(
                f"Dialogue: 0,{_ts(start)},{_ts(end)},Main,,0,0,0,,{text}"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys

    project_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest"
    script = json.loads((project_dir / "script.json").read_text())
    out = build_ass(script, project_dir / "captions.ass")
    print(f"Captions written to {out}")

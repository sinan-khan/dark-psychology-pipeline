"""
Stage 2+3: Topic Engine + Script Engine
Uses the free-tier Gemini API to pick an unused dark-psychology / manipulation
topic and turn it into a structured Hook -> Body -> Example -> Ending script,
with a highlight word per scene chosen by the model itself (so the caption
engine never has to guess which word turns yellow).
"""
import json
import os
import random
from pathlib import Path

import google.generativeai as genai

ROOT = Path(__file__).resolve().parent.parent
USED_TOPICS_FILE = ROOT / "config" / "used_topics.json"

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
MODEL = genai.GenerativeModel("gemini-2.0-flash")

SYSTEM_PROMPT = """You write scripts for a dark-psychology / manipulation-tactics
short-form video channel (35-55 second vertical videos). Tone: calm, direct,
slightly ominous. No sensationalism, no real named individuals, no illegal
instructions -- this is about recognizing manipulation patterns, not
performing them.

Return ONLY valid JSON, no markdown fences, matching this schema:
{
  "title": "string, <60 chars",
  "topic": "string, the specific manipulation tactic or pattern covered",
  "scenes": [
    {
      "text": "one sentence of narration",
      "visual_tags": ["2-4 lowercase concept tags for matching stock footage"],
      "highlight": "the single most important word or short phrase in this
                     sentence, verbatim as it appears in text, to render in
                     yellow"
    }
  ]
}

Structure: scene 1 = hook, scenes 2-4 = body/explanation, one scene = a
concrete example, last scene = a short closing line. 5-8 scenes total.
Each scene's narration should take roughly 3-6 seconds to speak aloud.
"""


def _load_used_topics() -> list[str]:
    if USED_TOPICS_FILE.exists():
        return json.loads(USED_TOPICS_FILE.read_text())
    return []


def _save_used_topic(topic: str) -> None:
    used = _load_used_topics()
    used.append(topic)
    USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_TOPICS_FILE.write_text(json.dumps(used, indent=2))


def generate_script(force_topic: str | None = None) -> dict:
    used = _load_used_topics()
    avoid_clause = (
        f"\nAvoid these already-covered topics: {', '.join(used[-40:])}."
        if used
        else ""
    )
    topic_instruction = (
        f'Write about this specific topic: "{force_topic}".'
        if force_topic
        else "Pick one specific, narrow manipulation tactic or dark-psychology "
        "pattern (not a broad theme)." + avoid_clause
    )

    prompt = f"{SYSTEM_PROMPT}\n\n{topic_instruction}"
    response = MODEL.generate_content(prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]

    data = json.loads(raw)
    _save_used_topic(data["topic"])
    return data


if __name__ == "__main__":
    import sys

    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "projects" / "latest" / "script.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    script = generate_script()
    out_path.write_text(json.dumps(script, indent=2))
    print(f"Script written to {out_path}")
    print(json.dumps(script, indent=2))

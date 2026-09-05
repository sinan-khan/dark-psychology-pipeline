"""
Stage 2+3: Topic Engine + Script Engine
Uses the free-tier Gemini API to pick an unused dark-psychology / manipulation
topic and turn it into a structured Hook -> Body -> Example -> Ending script,
with a highlight word per scene chosen by the model itself (so the caption
engine never has to guess which word turns yellow).
"""
import json
import os
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors

ROOT = Path(__file__).resolve().parent.parent
USED_TOPICS_FILE = ROOT / "config" / "used_topics.json"

CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
# Try the auto-updating Flash alias first, then fall back to other models if
# it's saturated -- demand spikes are usually model-specific, not account-wide,
# so trying a different model beats waiting longer on the same overloaded one.
MODEL_FALLBACKS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"]

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

CRITICAL LENGTH REQUIREMENT: the "text" fields across ALL scenes combined
must total between 100 and 130 words -- no fewer, no more. This is a hard
constraint, not a suggestion: count your words before finishing. This maps
to roughly 40-52 seconds of spoken narration at this voice's pace, which is
the actual target video length. A script with fewer than 100 total words
produces an unacceptably short video.
"""

MIN_TOTAL_WORDS = 85
MAX_TOTAL_WORDS = 145


def _load_used_topics() -> list[str]:
    if USED_TOPICS_FILE.exists():
        return json.loads(USED_TOPICS_FILE.read_text())
    return []


def _save_used_topic(topic: str) -> None:
    used = _load_used_topics()
    used.append(topic)
    USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_TOPICS_FILE.write_text(json.dumps(used, indent=2))


def _call_with_retry(prompt: str, attempts_per_model: int = 3, base_delay: int = 30):
    """Tries each model in MODEL_FALLBACKS in turn, retrying transient errors
    (503 overloaded, 429 rate-limited, 500/502/504) a few times per model
    before moving to the next one. Does NOT retry real problems (bad API key,
    malformed request, etc.) -- those fail the same way on every model."""
    retryable_codes = {429, 500, 502, 503, 504}
    last_error = None
    for model in MODEL_FALLBACKS:
        for attempt in range(1, attempts_per_model + 1):
            try:
                return CLIENT.models.generate_content(model=model, contents=prompt)
            except (genai_errors.ServerError, genai_errors.ClientError) as e:
                code = getattr(e, "code", None)
                last_error = e
                if code not in retryable_codes:
                    raise
                if attempt == attempts_per_model:
                    print(f"{model} still unavailable after {attempts_per_model} "
                          f"attempts, trying next model...")
                    break
                delay = base_delay * (2 ** (attempt - 1))
                print(f"Gemini call failed ({code}) on {model}: {e}. "
                      f"Retrying in {delay}s (attempt {attempt}/{attempts_per_model})...")
                time.sleep(delay)
    raise last_error


def _total_words(script: dict) -> int:
    return sum(len(scene["text"].split()) for scene in script["scenes"])


def generate_script(force_topic: str | None = None, _regen_attempt: int = 0) -> dict:
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
    response = _call_with_retry(prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):]

    data = json.loads(raw)

    word_count = _total_words(data)
    if not (MIN_TOTAL_WORDS <= word_count <= MAX_TOTAL_WORDS):
        max_regen_attempts = 2
        if _regen_attempt < max_regen_attempts:
            print(f"Script came back at {word_count} words (need "
                  f"{MIN_TOTAL_WORDS}-{MAX_TOTAL_WORDS}). Regenerating "
                  f"(attempt {_regen_attempt + 1}/{max_regen_attempts})...")
            return generate_script(force_topic=force_topic, _regen_attempt=_regen_attempt + 1)
        print(f"WARNING: proceeding with an out-of-range script ({word_count} "
              f"words) after {max_regen_attempts} regeneration attempts.")

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

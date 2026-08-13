"""AI-driven clip selection (PRD S6.1-S6.4, S8-S9).

The LLM only ever sees the transcript (segments + timestamps), never the
video itself (PRD S41: prefer sending text over video to external
providers). It returns candidate clips in the PRD S8 JSON shape; this
module validates/clamps them against the PRD S9 duration rules rather
than trusting the model to have followed instructions exactly.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig, complete_chat
from app.pipeline.ai_analysis.json_utils import extract_json
from app.pipeline.transcribe import TranscriptResult

MIN_DURATION = 15.0
DEFAULT_TARGET_MIN = 30.0
DEFAULT_TARGET_MAX = 60.0
MAX_DURATION = 180.0
AUTO_MIN_CLIPS = 3
AUTO_MAX_CLIPS = 10

_SYSTEM_PROMPT = """You are a viral short-form video editor. Given a timestamped \
transcript of a longer video, identify the moments most likely to work as standalone \
short vertical clips (YouTube Shorts / TikTok / Reels).

Rules:
- Each clip must be between {min_duration:.0f} and {max_duration:.0f} seconds long, \
ideally {target_min:.0f}-{target_max:.0f} seconds.
- Prefer a strong hook in the opening seconds, a clear curiosity gap or emotional \
moment, and a complete thought -- never cut off mid-sentence. Use the segment \
boundaries in the transcript as cut points.
- {count_instruction}
- Respond with ONLY a JSON object, no commentary, in exactly this shape:
{{"clips": [{{"start": <seconds>, "end": <seconds>, "score": <0-100>, \
"hook_score": <0-100>, "curiosity_score": <0-100>, "emotion_score": <0-100>, \
"information_score": <0-100>, "reason": "<short explanation>", \
"suggested_title": "<short punchy title>"}}]}}
"""


class CandidateClip(BaseModel):
    start: float
    end: float
    score: float
    hook_score: float
    curiosity_score: float
    emotion_score: float
    information_score: float
    reason: str
    suggested_title: str


def build_prompt(
    transcript: TranscriptResult,
    num_clips: int | None,
    min_duration: float = MIN_DURATION,
    target_min: float = DEFAULT_TARGET_MIN,
    target_max: float = DEFAULT_TARGET_MAX,
    max_duration: float = MAX_DURATION,
) -> tuple[str, str]:
    count_instruction = (
        f"Return exactly {num_clips} candidate clips."
        if num_clips is not None
        else (
            f"Decide the number of candidate clips yourself, based on how many genuinely strong moments "
            f"exist in this transcript -- typically {AUTO_MIN_CLIPS} to {AUTO_MAX_CLIPS}. Do not pad with "
            f"weak clips just to hit a number, and do not omit a strong moment to stay under one."
        )
    )
    system_prompt = _SYSTEM_PROMPT.format(
        count_instruction=count_instruction,
        min_duration=min_duration,
        target_min=target_min,
        target_max=target_max,
        max_duration=max_duration,
    )
    transcript_lines = "\n".join(f"[{seg.start:.2f}-{seg.end:.2f}] {seg.text}" for seg in transcript.segments)
    user_prompt = f"Transcript:\n{transcript_lines}"
    return system_prompt, user_prompt


def select_clips(
    config: ProviderConfig,
    transcript: TranscriptResult,
    num_clips: int | None,
    video_duration: float | None = None,
) -> list[CandidateClip]:
    system_prompt, user_prompt = build_prompt(transcript, num_clips)
    raw_response = complete_chat(config, system_prompt, user_prompt)
    parsed = extract_json(raw_response)

    raw_clips = parsed.get("clips", []) if isinstance(parsed, dict) else parsed
    if not isinstance(raw_clips, list):
        raise ValueError(f"Expected a list of clips, got: {type(raw_clips)}")

    candidates = [CandidateClip(**clip) for clip in raw_clips]
    return [c for c in candidates if _is_valid(c, video_duration)]


def _is_valid(clip: CandidateClip, video_duration: float | None) -> bool:
    if clip.end <= clip.start:
        return False
    duration = clip.end - clip.start
    if duration < MIN_DURATION or duration > MAX_DURATION:
        return False
    if video_duration is not None and clip.end > video_duration:
        return False
    return True

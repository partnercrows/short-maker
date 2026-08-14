"""AI-assisted spelling/grammar correction for a clip's subtitle lines.

A preview-only step: `correct_subtitle_lines()` never touches the persisted
`SubtitleDocument` itself -- the API layer returns suggestions for the user
to review, and an accepted correction is applied the same way any other
manual text edit is (through the existing `PUT /subtitles/{clip_id}/document`
endpoint), so id/timing/style safety and the "clear stale `words`" rule stay
enforced by code already proven correct rather than being duplicated here.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig, complete_chat
from app.pipeline.ai_analysis.json_utils import extract_json
from app.pipeline.subtitle.models import SubtitleDocumentLine

_SYSTEM_PROMPT = """You are a subtitle proofreader fixing spelling, grammar, and punctuation \
mistakes in a video transcript. Keep whatever language the text is already in -- never \
translate. Do not change the meaning, tone, or word choice beyond fixing clear mistakes, and \
do not add or remove content. Correct each line independently; do not merge, split, or \
reorder lines. If a line already has no errors, return its text unchanged.

Respond with ONLY a JSON array, no commentary, in exactly this shape:
[{"id": "<line id>", "corrected_text": "<corrected line text>"}, ...]

Return exactly one object per input line, reusing the same "id" values you were given.
"""


class SubtitleCorrection(BaseModel):
    id: str
    corrected_text: str


def build_correction_prompt(lines: list[SubtitleDocumentLine]) -> tuple[str, str]:
    payload = [{"id": line.id, "text": line.text} for line in lines]
    user_prompt = "Subtitle lines (JSON array):\n" + json.dumps(payload, ensure_ascii=False)
    return _SYSTEM_PROMPT, user_prompt


def correct_subtitle_lines(config: ProviderConfig, lines: list[SubtitleDocumentLine]) -> list[SubtitleCorrection]:
    system_prompt, user_prompt = build_correction_prompt(lines)
    raw_response = complete_chat(config, system_prompt, user_prompt)
    parsed = extract_json(raw_response)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of corrections from the AI provider")

    valid_ids = {line.id for line in lines}
    corrections: list[SubtitleCorrection] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        line_id = item.get("id")
        corrected_text = item.get("corrected_text")
        if line_id not in valid_ids or not isinstance(corrected_text, str):
            continue
        corrections.append(SubtitleCorrection(id=line_id, corrected_text=corrected_text))
    return corrections

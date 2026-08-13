"""Social Kit generation (PRD S23-27): viral titles, a platform-appropriate
description, hashtags, and a thumbnail idea for one already-generated clip.

Never re-runs Whisper, Active Speaker, or FFmpeg (PRD S28) -- it only ever
sees the clip's already-stored analysis + transcript text, the same way
clip_selector only ever sees transcript text (PRD S41).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig, complete_chat
from app.pipeline.ai_analysis.json_utils import extract_json

PLATFORMS = ["youtube_shorts", "tiktok", "instagram_reels", "facebook_reels"]

_SYSTEM_PROMPT = """You are a social media growth expert writing a publishing kit for one \
short-form vertical video clip, targeting {platform}.

Respond with ONLY a JSON object, no commentary, in exactly this shape:
{{"titles": [{{"title": "<punchy title>", "score": <0-100>}}, {{"title": "<punchy title>", \
"score": <0-100>}}, {{"title": "<punchy title>", "score": <0-100>}}], \
"description": "<platform-appropriate description, end with a call to action>", \
"hashtags": ["<tag1>", "<tag2>", "<tag3>", "<tag4>", "<tag5>"], \
"thumbnail_idea": "<a short visual description of an eye-catching thumbnail for this clip>", \
"thumbnail_prompt": "<a detailed prompt suitable for an AI image generator to create that thumbnail>"}}

Always return exactly 3 title options, each with its own virality score.
"""


class TitleOption(BaseModel):
    title: str
    score: float


class SocialKitContent(BaseModel):
    titles: list[TitleOption]
    description: str
    hashtags: list[str]
    thumbnail_idea: str
    thumbnail_prompt: str


def build_prompt(clip_summary: str, platform: str) -> tuple[str, str]:
    system_prompt = _SYSTEM_PROMPT.format(platform=platform)
    user_prompt = f"Clip content:\n{clip_summary}"
    return system_prompt, user_prompt


def generate_social_kit(config: ProviderConfig, clip_summary: str, platform: str) -> SocialKitContent:
    system_prompt, user_prompt = build_prompt(clip_summary, platform)
    raw_response = complete_chat(config, system_prompt, user_prompt)
    parsed = extract_json(raw_response)
    return SocialKitContent(**parsed)

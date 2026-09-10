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


# A recipe video is not sold the way a talking-head clip is: the hook is the
# dish, the promise is "you could cook this", and the caption carries a
# save-for-later. Same engine, same storage, different words (PRD S31/S32).
_RECIPE_SYSTEM_PROMPT = """You are writing the publishing kit for one short cooking video on {platform}.

The video is a long cooking session condensed into about a minute: the finished dish, then the cooking \
process from preparation to plating.

Write in {language}.

Rules:
- Titles must name the dish and promise something concrete (simple, quick, the sauce soaks in).
- Never claim an ingredient or a step that is not in the recipe summary you are given.
- The CTA should suit food content: saving the recipe for later, trying it at the weekend.
- Thumbnail text is at most 4 words, in two short lines.
- Respond with ONLY a JSON object, no commentary, in exactly this shape:
{{"titles": [{{"title": "<title>", "score": <0-100>}}, {{"title": "<title>", "score": <0-100>}}, \
{{"title": "<title>", "score": <0-100>}}], \
"alternative_hooks": ["<short opening hook>", "<short opening hook>"], \
"description": "<caption describing the dish and the process>", \
"hashtags": ["<tag1>", "<tag2>", "<tag3>", "<tag4>", "<tag5>"], \
"cta": "<one short call to action>", \
"thumbnail_text": "<max 4 words>", \
"thumbnail_idea": "<short visual description of the thumbnail>", \
"thumbnail_prompt": "<detailed prompt for an AI image generator>"}}
"""


class RecipeSocialKitExtras(BaseModel):
    """The recipe-only half of the kit (PRD S31). Stored in
    `social_kits.extra_json` so the shared columns keep their meaning."""

    alternative_hooks: list[str] = []
    cta: str = ""
    thumbnail_text: str = ""


def build_recipe_prompt(recipe_summary: str, platform: str, language: str = "id") -> tuple[str, str]:
    system_prompt = _RECIPE_SYSTEM_PROMPT.format(
        platform=platform, language="Indonesian" if language == "id" else "English"
    )
    return system_prompt, f"Recipe summary:\n{recipe_summary}"


def generate_recipe_social_kit(
    config: ProviderConfig, recipe_summary: str, platform: str, language: str = "id"
) -> tuple[SocialKitContent, RecipeSocialKitExtras]:
    system_prompt, user_prompt = build_recipe_prompt(recipe_summary, platform, language)
    parsed = extract_json(complete_chat(config, system_prompt, user_prompt))
    content = SocialKitContent(
        titles=[TitleOption(**title) for title in parsed.get("titles", [])],
        description=str(parsed.get("description", "")),
        hashtags=[str(tag) for tag in parsed.get("hashtags", [])],
        thumbnail_idea=str(parsed.get("thumbnail_idea", "")),
        thumbnail_prompt=str(parsed.get("thumbnail_prompt", "")),
    )
    extras = RecipeSocialKitExtras(
        alternative_hooks=[str(hook) for hook in parsed.get("alternative_hooks", [])][:4],
        cta=str(parsed.get("cta", "")),
        thumbnail_text=str(parsed.get("thumbnail_text", "")),
    )
    return content, extras

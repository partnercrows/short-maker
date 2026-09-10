from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig
from app.api.schemas import SocialKit
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.pipeline.recipe import recipe_analyzer, store
from app.core.config import get_settings
from app.pipeline.social_kit import (
    RecipeSocialKitExtras,
    SocialKitContent,
    generate_recipe_social_kit,
    generate_social_kit,
)

router = APIRouter(prefix="/social-kit", tags=["social_kit"], dependencies=[Depends(require_local_token)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SocialKitRequest(BaseModel):
    platform: str
    provider: ProviderConfig


@router.get("/{clip_id}", response_model=list[SocialKit])
def get_social_kits(clip_id: str) -> list[SocialKit]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM social_kits WHERE clip_id = ? ORDER BY created_at DESC", (clip_id,)).fetchall()
    return [SocialKit(**dict(row)) for row in rows]


@router.post("/{clip_id}/generate", response_model=SocialKit)
def generate_social_kit_endpoint(clip_id: str, request: SocialKitRequest) -> SocialKit:
    return _generate_and_save(clip_id, request.platform, request.provider)


@router.post("/{clip_id}/regenerate", response_model=SocialKit)
def regenerate_social_kit_endpoint(clip_id: str, request: SocialKitRequest) -> SocialKit:
    """Per PRD S28: regeneration touches Social Kit only -- it never re-runs
    Whisper, Active Speaker, or FFmpeg rendering. `_generate_and_save` already
    only reads the clip's stored analysis/transcript text, so regenerate is
    exactly the same call as generate; the distinction is purely semantic."""
    return _generate_and_save(clip_id, request.platform, request.provider)


def _generate_and_save(clip_id: str, platform: str, provider: ProviderConfig) -> SocialKit:
    clip = _get_clip_or_404(clip_id)
    recipe = _recipe_context(clip)
    try:
        if recipe is not None:
            summary, language = recipe
            content, extras = generate_recipe_social_kit(provider, summary, platform, language)
        else:
            content, extras = generate_social_kit(provider, _build_clip_summary(clip), platform), None
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user as a plain message
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _save_social_kit(clip_id, platform, content, extras)


def _recipe_context(clip) -> tuple[str, str] | None:
    """The recipe summary to write a kit from, or None for an AI Clipper clip.

    A recipe video's own analysis says far more than its (empty) transcript
    column would -- the dish, the ingredients that were actually seen, and the
    steps in order.
    """
    if store.project_mode(clip["project_id"]) != "recipe":
        return None
    analysis = recipe_analyzer.load_analysis(get_settings().recipe_analysis_path(clip["project_id"]))
    if analysis is None:
        return None

    scenes = [scene for scene in store.load_scenes(clip["id"]) if scene.enabled]
    parts = [f"Dish: {analysis.recipe_name or 'unknown'}"]
    if analysis.main_ingredient:
        parts.append(f"Main ingredient: {analysis.main_ingredient}")
    if analysis.ingredients:
        parts.append("Ingredients seen: " + ", ".join(i.name for i in analysis.ingredients))
    if analysis.possible_ingredients:
        parts.append("Possible (uncertain) ingredients: " + ", ".join(analysis.possible_ingredients))
    if scenes:
        parts.append("Steps in the video: " + " -> ".join(scene.title for scene in scenes))
        parts.append(f"Length: about {int(sum(scene.duration for scene in scenes))} seconds")
    return "\n".join(parts), analysis.language


def _get_clip_or_404(clip_id: str):
    with get_connection() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


def _build_clip_summary(clip) -> str:
    parts: list[str] = []
    if clip["analysis_json"]:
        try:
            analysis = json.loads(clip["analysis_json"])
        except json.JSONDecodeError:
            analysis = {}
        if analysis.get("suggested_title"):
            parts.append(f"Working title: {analysis['suggested_title']}")
        if analysis.get("reason"):
            parts.append(f"Why it's compelling: {analysis['reason']}")

    if clip["transcript_json"]:
        try:
            segments = json.loads(clip["transcript_json"])
        except json.JSONDecodeError:
            segments = []
        transcript_text = " ".join(s.get("text", "") for s in segments).strip()
        if transcript_text:
            parts.append(f"Transcript: {transcript_text}")

    if not parts:
        raise HTTPException(
            status_code=400, detail="This clip has no analysis or transcript to build a Social Kit from yet."
        )
    return "\n\n".join(parts)


def _save_social_kit(
    clip_id: str, platform: str, content: SocialKitContent, extras: RecipeSocialKitExtras | None = None
) -> SocialKit:
    now = _now()
    titles_json = json.dumps([t.model_dump() for t in content.titles])
    hashtags = " ".join(f"#{h.lstrip('#')}" for h in content.hashtags)
    extra_json = json.dumps(extras.model_dump()) if extras else None

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM social_kits WHERE clip_id = ? AND platform = ?", (clip_id, platform)
        ).fetchone()

        if existing:
            social_kit_id = existing["id"]
            conn.execute(
                """
                UPDATE social_kits SET titles_json = ?, description = ?, hashtags = ?,
                    thumbnail_idea = ?, thumbnail_prompt = ?, extra_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    titles_json,
                    content.description,
                    hashtags,
                    content.thumbnail_idea,
                    content.thumbnail_prompt,
                    extra_json,
                    now,
                    social_kit_id,
                ),
            )
        else:
            social_kit_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO social_kits (
                    id, clip_id, platform, titles_json, description, hashtags,
                    thumbnail_idea, thumbnail_prompt, extra_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    social_kit_id,
                    clip_id,
                    platform,
                    titles_json,
                    content.description,
                    hashtags,
                    content.thumbnail_idea,
                    content.thumbnail_prompt,
                    extra_json,
                    now,
                    now,
                ),
            )

        next_version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM social_kit_versions WHERE social_kit_id = ?",
            (social_kit_id,),
        ).fetchone()["v"]
        conn.execute(
            "INSERT INTO social_kit_versions (id, social_kit_id, version, content_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                social_kit_id,
                next_version,
                json.dumps({**content.model_dump(), **(extras.model_dump() if extras else {})}),
                now,
            ),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM social_kits WHERE id = ?", (social_kit_id,)).fetchone()

    return SocialKit(**dict(row))

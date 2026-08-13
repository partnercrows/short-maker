from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import SocialKit
from app.core.security import require_local_token
from app.db.connection import get_connection

router = APIRouter(prefix="/social-kit", tags=["social_kit"], dependencies=[Depends(require_local_token)])


@router.get("/{clip_id}", response_model=list[SocialKit])
def get_social_kits(clip_id: str) -> list[SocialKit]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM social_kits WHERE clip_id = ? ORDER BY created_at DESC", (clip_id,)).fetchall()
    return [SocialKit(**dict(row)) for row in rows]


@router.post("/{clip_id}/generate")
def generate_social_kit(clip_id: str, platform: str) -> None:
    raise HTTPException(status_code=501, detail="Social Kit generation lands with the MVP AI-provider pipeline pass.")


@router.post("/{clip_id}/regenerate")
def regenerate_social_kit(clip_id: str, platform: str) -> None:
    """Per PRD S28: regeneration touches Social Kit only — never re-runs
    Whisper, Active Speaker, or FFmpeg rendering. This contract shapes the
    route (clip video state is untouched by this call) even before real
    generation logic exists."""
    raise HTTPException(status_code=501, detail="Social Kit regeneration lands with the MVP AI-provider pipeline pass.")

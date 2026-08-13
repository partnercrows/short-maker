from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_local_token
from app.db.connection import get_connection
from app.pipeline.subtitle import SubtitleRenderer

router = APIRouter(prefix="/subtitles", tags=["subtitles"], dependencies=[Depends(require_local_token)])


@router.get("/{clip_id}")
def get_subtitle_state(clip_id: str) -> dict:
    """Subtitle state is independent of clip video generation (PRD S18):
    a clip can exist with `has_subtitle: false` and gain one later without
    re-rendering the underlying video."""
    with get_connection() as conn:
        row = conn.execute("SELECT id, subtitle_path, transcript_json FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {
        "clip_id": row["id"],
        "subtitle_path": row["subtitle_path"],
        "has_subtitle": row["subtitle_path"] is not None,
        "transcript_json": row["transcript_json"],
    }


@router.post("/{clip_id}/render")
def render_subtitle(clip_id: str) -> dict:
    try:
        SubtitleRenderer().render_ass(transcript_json="", style={})
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return {"clip_id": clip_id}  # pragma: no cover - unreachable until MVP rendering lands

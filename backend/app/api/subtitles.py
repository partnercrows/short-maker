from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig
from app.core.config import get_settings
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_render_subtitle_job
from app.pipeline.subtitle import build_initial_document, load_clip_words
from app.pipeline.subtitle.correction import SubtitleCorrection, correct_subtitle_lines
from app.pipeline.subtitle.models import SubtitleDocument, SubtitleStyle, load_document, save_document

router = APIRouter(prefix="/subtitles", tags=["subtitles"], dependencies=[Depends(require_local_token)])


class SubtitleDocumentResponse(BaseModel):
    document: SubtitleDocument
    needs_rebuild: bool
    rendered_video_path: str | None = None  # the subtitle-free master, for live-preview overlay


class ApplyStyleRequest(BaseModel):
    scope: str  # "line" | "lines" | "clip"
    line_ids: list[str] | None = None
    style: SubtitleStyle


def _get_clip_or_404(clip_id: str):
    with get_connection() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/{clip_id}", response_model=SubtitleDocumentResponse)
def get_subtitle_document(clip_id: str) -> SubtitleDocumentResponse:
    """Subtitle state is independent of clip video generation (PRD S18): a
    clip can exist with no document yet and gain one later without
    re-rendering the underlying video. Lazily creates+persists the document
    (seeded from the project transcript) on first call."""
    clip = _get_clip_or_404(clip_id)
    settings = get_settings()

    subtitle_json_path = settings.clip_subtitle_json_path(clip["project_id"], clip_id)
    if subtitle_json_path.is_file():
        document = load_document(subtitle_json_path)
    else:
        transcript_path = settings.project_analysis_dir(clip["project_id"]) / "transcript.json"
        if not transcript_path.is_file():
            raise HTTPException(status_code=400, detail="This project has no transcript yet -- run Analyze first.")
        words = load_clip_words(transcript_path, clip["start_time"], clip["end_time"])
        document = build_initial_document(clip_id, words)
        save_document(subtitle_json_path, document)
        with get_connection() as conn:
            conn.execute(
                "UPDATE clips SET subtitle_json_path = ?, updated_at = ? WHERE id = ?",
                (str(subtitle_json_path), _now(), clip_id),
            )
            conn.commit()

    rendered_path = settings.clip_rendered_path(clip["project_id"], clip_id)
    needs_rebuild = not rendered_path.is_file()
    return SubtitleDocumentResponse(
        document=document, needs_rebuild=needs_rebuild, rendered_video_path=None if needs_rebuild else str(rendered_path)
    )


@router.put("/{clip_id}/document", response_model=SubtitleDocument)
def save_subtitle_document(clip_id: str, document: SubtitleDocument) -> SubtitleDocument:
    """Replaces the whole document in one call -- text edits, timing
    changes, split/merge/add/delete are all just a new `lines[]` array
    computed client-side, since there's no server-side undo/redo to
    preserve by breaking this into granular per-operation endpoints."""
    clip = _get_clip_or_404(clip_id)

    ids = [line.id for line in document.lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Duplicate line ids in document")
    for line in document.lines:
        if line.start >= line.end:
            raise HTTPException(status_code=400, detail=f"Line {line.id}: start must be before end")

    document.lines.sort(key=lambda line: line.start)
    document.clip_id = clip_id
    document.updated_at = _now()

    settings = get_settings()
    path = settings.clip_subtitle_json_path(clip["project_id"], clip_id)
    save_document(path, document)
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET subtitle_json_path = ?, updated_at = ? WHERE id = ?", (str(path), document.updated_at, clip_id)
        )
        conn.commit()
    return document


@router.post("/{clip_id}/style", response_model=SubtitleDocument)
def apply_subtitle_style(clip_id: str, request: ApplyStyleRequest) -> SubtitleDocument:
    """`scope="clip"` updates the document's default style (affecting every
    line with no override, including future ones) -- semantically different
    from fanning the same style across explicit lines, which is why this
    isn't folded into the generic document PUT."""
    clip = _get_clip_or_404(clip_id)
    settings = get_settings()
    path = settings.clip_subtitle_json_path(clip["project_id"], clip_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No subtitle document yet -- fetch it first")
    document = load_document(path)

    if request.scope == "clip":
        document.default_style = request.style
    elif request.scope == "line":
        if not request.line_ids or len(request.line_ids) != 1:
            raise HTTPException(status_code=400, detail="scope='line' requires exactly one line_id")
        _apply_style_to_lines(document, request.line_ids, request.style)
    elif request.scope == "lines":
        if not request.line_ids:
            raise HTTPException(status_code=400, detail="scope='lines' requires at least one line_id")
        _apply_style_to_lines(document, request.line_ids, request.style)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scope: {request.scope!r}")

    document.updated_at = _now()
    save_document(path, document)
    with get_connection() as conn:
        conn.execute("UPDATE clips SET updated_at = ? WHERE id = ?", (document.updated_at, clip_id))
        conn.commit()
    return document


def _apply_style_to_lines(document: SubtitleDocument, line_ids: list[str], style: SubtitleStyle) -> None:
    ids = set(line_ids)
    matched = {line.id for line in document.lines} & ids
    missing = ids - matched
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown line id(s): {sorted(missing)}")
    for line in document.lines:
        if line.id in ids:
            line.style = style


class CorrectSubtitlesRequest(BaseModel):
    provider: ProviderConfig
    line_ids: list[str] | None = None  # None = every line in the document


class CorrectSubtitlesResponse(BaseModel):
    corrections: list[SubtitleCorrection]


@router.post("/{clip_id}/correct", response_model=CorrectSubtitlesResponse)
def correct_subtitles(clip_id: str, request: CorrectSubtitlesRequest) -> CorrectSubtitlesResponse:
    """Preview-only: returns AI-suggested spelling/grammar fixes without
    touching the persisted document. The frontend shows these for review and
    applies accepted ones through the existing document PUT, same as any
    other manual text edit."""
    clip = _get_clip_or_404(clip_id)
    settings = get_settings()
    path = settings.clip_subtitle_json_path(clip["project_id"], clip_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No subtitle document yet -- fetch it first")
    document = load_document(path)

    lines = document.lines
    if request.line_ids is not None:
        wanted = set(request.line_ids)
        missing = wanted - {line.id for line in lines}
        if missing:
            raise HTTPException(status_code=404, detail=f"Unknown line id(s): {sorted(missing)}")
        lines = [line for line in lines if line.id in wanted]
    if not lines:
        raise HTTPException(status_code=400, detail="No subtitle lines to correct")

    try:
        corrections = correct_subtitle_lines(request.provider, lines)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user as a plain message
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CorrectSubtitlesResponse(corrections=corrections)


@router.post("/{clip_id}/render", response_model=Job)
def render_subtitle(clip_id: str) -> Job:
    clip = _get_clip_or_404(clip_id)
    job = job_manager.create(JobType.RENDER_SUBTITLE, project_id=clip["project_id"])
    thread = threading.Thread(target=run_render_subtitle_job, args=(job.id, clip_id), daemon=True)
    thread.start()
    return job

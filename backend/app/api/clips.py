from __future__ import annotations

import subprocess
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.schemas import Clip, GenerateClipRequest
from app.core.config import get_settings
from app.core.ffmpeg_utils import convert_image_to_png, extract_frame
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_export_clip_job, run_generate_job
from app.pipeline.intro import IntroFrame, load_intro_frame, save_intro_frame

router = APIRouter(prefix="/clips", tags=["clips"], dependencies=[Depends(require_local_token)])

ALLOWED_INTRO_UPLOAD_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class CopyClipRequest(BaseModel):
    destination_folder: str


class CaptureIntroFrameRequest(BaseModel):
    timestamp: float
    duration_seconds: float = 2.0


class UpdateIntroFrameRequest(BaseModel):
    enabled: bool
    duration_seconds: float


class IntroFrameResponse(BaseModel):
    intro: IntroFrame
    image_path: str | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_clip_row(clip_id: str):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return row


@router.get("", response_model=list[Clip])
def list_clips(project_id: str | None = None) -> list[Clip]:
    query = "SELECT * FROM clips"
    params: tuple = ()
    if project_id is not None:
        query += " WHERE project_id = ?"
        params = (project_id,)
    query += " ORDER BY start_time ASC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [Clip(**dict(row)) for row in rows]


@router.get("/{clip_id}", response_model=Clip)
def get_clip(clip_id: str) -> Clip:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    return Clip(**dict(row))


@router.delete("/{clip_id}", status_code=204)
def delete_clip(clip_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
        conn.commit()


@router.post("/{clip_id}/copy-to", response_model=Job)
def copy_clip_to(clip_id: str, payload: CopyClipRequest) -> Job:
    row = _get_clip_row(clip_id)
    if not row["video_path"]:
        raise HTTPException(status_code=400, detail="This clip hasn't been generated yet")
    job = job_manager.create(JobType.EXPORT_CLIP, project_id=row["project_id"])
    thread = threading.Thread(
        target=run_export_clip_job,
        args=(job.id, clip_id, payload.destination_folder),
        daemon=True,
    )
    thread.start()
    return job


@router.get("/{clip_id}/intro", response_model=IntroFrameResponse)
def get_intro_frame(clip_id: str) -> IntroFrameResponse:
    clip = _get_clip_row(clip_id)
    settings = get_settings()
    intro_json_path = settings.clip_intro_json_path(clip["project_id"], clip_id)
    intro = load_intro_frame(intro_json_path) if intro_json_path.is_file() else IntroFrame(created_at=_now())
    image_path = settings.clip_intro_image_path(clip["project_id"], clip_id)
    return IntroFrameResponse(intro=intro, image_path=str(image_path) if image_path.is_file() else None)


@router.put("/{clip_id}/intro", response_model=IntroFrameResponse)
def update_intro_frame(clip_id: str, payload: UpdateIntroFrameRequest) -> IntroFrameResponse:
    """Toggles enabled/duration only -- capturing or uploading a new image
    goes through the dedicated endpoints below since those also decide
    `source`/`source_timestamp`."""
    clip = _get_clip_row(clip_id)
    settings = get_settings()
    intro_json_path = settings.clip_intro_json_path(clip["project_id"], clip_id)
    intro = load_intro_frame(intro_json_path) if intro_json_path.is_file() else IntroFrame(created_at=_now())
    intro.enabled = payload.enabled
    intro.duration_seconds = payload.duration_seconds
    save_intro_frame(intro_json_path, intro)
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET intro_json_path = ?, updated_at = ? WHERE id = ?", (str(intro_json_path), _now(), clip_id)
        )
        conn.commit()
    image_path = settings.clip_intro_image_path(clip["project_id"], clip_id)
    return IntroFrameResponse(intro=intro, image_path=str(image_path) if image_path.is_file() else None)


@router.post("/{clip_id}/intro/capture", response_model=IntroFrameResponse)
def capture_intro_frame(clip_id: str, payload: CaptureIntroFrameRequest) -> IntroFrameResponse:
    clip = _get_clip_row(clip_id)
    settings = get_settings()
    rendered_path = settings.clip_rendered_path(clip["project_id"], clip_id)
    source_video = str(rendered_path) if rendered_path.is_file() else clip["video_path"]
    if not source_video:
        raise HTTPException(status_code=400, detail="This clip hasn't been generated yet")

    image_path = settings.clip_intro_image_path(clip["project_id"], clip_id)
    try:
        extract_frame(source_video, payload.timestamp, str(image_path))
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to capture frame: {exc}") from exc

    intro_json_path = settings.clip_intro_json_path(clip["project_id"], clip_id)
    intro = IntroFrame(
        enabled=True,
        source="captured",
        source_timestamp=payload.timestamp,
        duration_seconds=payload.duration_seconds,
        created_at=_now(),
    )
    save_intro_frame(intro_json_path, intro)
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET intro_json_path = ?, updated_at = ? WHERE id = ?", (str(intro_json_path), _now(), clip_id)
        )
        conn.commit()
    return IntroFrameResponse(intro=intro, image_path=str(image_path))


@router.post("/{clip_id}/intro/upload", response_model=IntroFrameResponse)
async def upload_intro_frame(
    clip_id: str, duration_seconds: float = Form(2.0), file: UploadFile = File(...)
) -> IntroFrameResponse:
    clip = _get_clip_row(clip_id)
    if file.content_type not in ALLOWED_INTRO_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.content_type}")

    settings = get_settings()
    clip_dir = settings.clip_dir(clip["project_id"], clip_id)
    clip_dir.mkdir(parents=True, exist_ok=True)
    suffix = ALLOWED_INTRO_UPLOAD_TYPES[file.content_type]
    temp_upload_path = clip_dir / f"intro_upload{suffix}"
    temp_upload_path.write_bytes(await file.read())

    image_path = settings.clip_intro_image_path(clip["project_id"], clip_id)
    try:
        convert_image_to_png(str(temp_upload_path), str(image_path))
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process uploaded image: {exc}") from exc
    finally:
        temp_upload_path.unlink(missing_ok=True)

    intro_json_path = settings.clip_intro_json_path(clip["project_id"], clip_id)
    intro = IntroFrame(enabled=True, source="uploaded", source_timestamp=None, duration_seconds=duration_seconds, created_at=_now())
    save_intro_frame(intro_json_path, intro)
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET intro_json_path = ?, updated_at = ? WHERE id = ?", (str(intro_json_path), _now(), clip_id)
        )
        conn.commit()
    return IntroFrameResponse(intro=intro, image_path=str(image_path))


@router.post("/{clip_id}/generate", response_model=Job)
def generate_clip(clip_id: str, payload: GenerateClipRequest) -> Job:
    clip = get_clip(clip_id)  # 404s if missing
    job = job_manager.create(JobType.GENERATE_CLIP, project_id=clip.project_id)
    thread = threading.Thread(
        target=run_generate_job,
        args=(job.id, clip_id, payload.include_subtitle, payload.output_folder),
        daemon=True,
    )
    thread.start()
    return job

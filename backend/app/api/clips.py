from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import Clip, GenerateClipRequest
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_generate_job

router = APIRouter(prefix="/clips", tags=["clips"], dependencies=[Depends(require_local_token)])


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

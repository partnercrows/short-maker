from __future__ import annotations

import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AnalyzeRequest, Project, ProjectCreate
from app.core.config import get_settings
from app.core.ffmpeg_utils import probe_metadata
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_analyze_job

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(require_local_token)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", response_model=Project)
def create_project(payload: ProjectCreate) -> Project:
    if not Path(payload.source_video_path).is_file():
        raise HTTPException(status_code=400, detail=f"Video file not found: {payload.source_video_path}")

    project_id = str(uuid.uuid4())
    now = _now()
    settings = get_settings()

    # Copy once into project storage (PRD S16/S35) rather than referencing the
    # original path indefinitely -- the source shouldn't break if the user
    # moves/deletes the file they picked.
    dest_path = settings.project_source_path(project_id)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(payload.source_video_path, dest_path)

    metadata = probe_metadata(str(dest_path))

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, source_video_path, source_duration, source_resolution, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (project_id, payload.name, str(dest_path), metadata.duration, f"{metadata.width}x{metadata.height}", now, now),
        )
        conn.commit()
    return get_project(project_id)


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [Project(**dict(row)) for row in rows]


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(**dict(row))


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


@router.post("/{project_id}/analyze", response_model=Job)
def analyze_project(project_id: str, payload: AnalyzeRequest) -> Job:
    get_project(project_id)  # 404s if missing, before we bother creating a job
    job = job_manager.create(JobType.ANALYZE_VIDEO, project_id=project_id)
    thread = threading.Thread(
        target=run_analyze_job, args=(job.id, project_id, payload.provider, payload.num_clips), daemon=True
    )
    thread.start()
    return job

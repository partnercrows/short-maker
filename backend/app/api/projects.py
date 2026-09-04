from __future__ import annotations

import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import AnalyzeRequest, DeleteProjectsResult, Project, ProjectCreate
from app.core.config import get_settings
from app.core.ffmpeg_utils import probe_metadata
from app.core.project_storage import StorageDeletion, delete_directory, directory_bytes
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

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    # Checked before the copy, not after: copying the source is the slow part
    # (seconds to minutes for a large video), and there's no reason to spend
    # that time -- or the gigabyte of disk it takes -- on a project that is
    # about to be rejected.
    _raise_if_name_taken(name)

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

    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, source_video_path, source_duration, source_resolution, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (project_id, name, str(dest_path), metadata.duration, f"{metadata.width}x{metadata.height}", now, now),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        # Two requests for the same name that both passed the check above
        # before either inserted -- the unique index is what actually decides
        # it. Take the copied video back down with the losing request, or the
        # rejection would still cost the user a gigabyte.
        delete_directory(settings.project_dir(project_id))
        raise HTTPException(status_code=409, detail=_name_taken_detail(name)) from exc
    return get_project(project_id)


def _raise_if_name_taken(name: str) -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM projects WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail=_name_taken_detail(name))


def _name_taken_detail(name: str) -> str:
    return (
        f'A project named "{name}" already exists. Open it from History to see its clips, '
        "or pick a different name for this one."
    )


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [_with_storage(dict(row)) for row in rows]


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str) -> Project:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _with_storage(dict(row))


def _with_storage(row: dict) -> Project:
    """`storage_bytes` is measured, not stored: it's what the project's folder
    actually occupies right now, which is what the delete confirmation needs
    to be honest about how much space removing it frees."""
    settings = get_settings()
    return Project(**row, storage_bytes=directory_bytes(settings.project_dir(row["id"])))


@router.delete("", response_model=DeleteProjectsResult)
def delete_all_projects() -> DeleteProjectsResult:
    """Clears the whole history. Each project's folder goes with it -- the
    point of the action is reclaiming the disk, not just emptying a list."""
    with get_connection() as conn:
        project_ids = [row["id"] for row in conn.execute("SELECT id FROM projects").fetchall()]

    deletion = StorageDeletion()
    for project_id in project_ids:
        deletion = deletion.merge(_delete_project_storage(project_id))

    with get_connection() as conn:
        conn.execute("DELETE FROM projects")
        conn.commit()

    return DeleteProjectsResult(
        deleted_projects=len(project_ids), freed_bytes=deletion.freed_bytes, failed_paths=deletion.failed_paths
    )


@router.delete("/{project_id}", response_model=DeleteProjectsResult)
def delete_project(project_id: str) -> DeleteProjectsResult:
    get_project(project_id)  # 404s if it's already gone, before deleting anything
    deletion = _delete_project_storage(project_id)

    # Clips, social kits and jobs all cascade off this row (schema.py), and
    # the row goes even if some file underneath refused to be deleted --
    # leaving the history entry behind would make the failure unfixable from
    # the UI. The paths that survived are reported instead.
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()

    return DeleteProjectsResult(
        deleted_projects=1, freed_bytes=deletion.freed_bytes, failed_paths=deletion.failed_paths
    )


def _delete_project_storage(project_id: str) -> StorageDeletion:
    return delete_directory(get_settings().project_dir(project_id))


@router.post("/{project_id}/analyze", response_model=Job)
def analyze_project(project_id: str, payload: AnalyzeRequest) -> Job:
    get_project(project_id)  # 404s if missing, before we bother creating a job
    job = job_manager.create(JobType.ANALYZE_VIDEO, project_id=project_id)
    thread = threading.Thread(
        target=run_analyze_job,
        args=(job.id, project_id, payload.provider, payload.num_clips, payload.use_gpu),
        daemon=True
    )
    thread.start()
    return job

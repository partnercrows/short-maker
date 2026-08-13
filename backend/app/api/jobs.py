from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_local_token
from app.jobs.manager import job_manager
from app.jobs.models import Job

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_local_token)])


@router.get("", response_model=list[Job])
def list_jobs(project_id: str | None = None) -> list[Job]:
    return job_manager.list(project_id=project_id)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str) -> Job:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job_manager.cancel(job_id)
    return job_manager.get(job_id)  # type: ignore[return-value]

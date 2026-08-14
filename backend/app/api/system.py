"""Device capability probing, so the Settings UI can show whether GPU
transcription is actually usable on this machine rather than just
offering a toggle that might silently fail. Also exposes the on-demand GPU
pack download (see app.core.gpu_pack).
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.gpu_pack import is_gpu_pack_installed
from app.core.security import require_local_token
from app.core.system_capabilities import SystemCapabilities, probe_capabilities
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_download_gpu_pack_job

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_local_token)])


class GpuPackStatus(BaseModel):
    installed: bool


@router.get("/capabilities", response_model=SystemCapabilities)
def get_capabilities() -> SystemCapabilities:
    return probe_capabilities()


@router.get("/gpu-pack", response_model=GpuPackStatus)
def get_gpu_pack_status() -> GpuPackStatus:
    return GpuPackStatus(installed=is_gpu_pack_installed())


@router.post("/gpu-pack/download", response_model=Job)
def download_gpu_pack_endpoint() -> Job:
    job = job_manager.create(JobType.DOWNLOAD_GPU_PACK)
    thread = threading.Thread(target=run_download_gpu_pack_job, args=(job.id,), daemon=True)
    thread.start()
    return job

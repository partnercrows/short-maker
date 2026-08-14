from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    ANALYZE_VIDEO = "analyze_video"
    GENERATE_CLIP = "generate_clip"
    RENDER_SUBTITLE = "render_subtitle"
    GENERATE_SOCIAL_KIT = "generate_social_kit"
    DOWNLOAD_GPU_PACK = "download_gpu_pack"
    EXPORT_CLIP = "export_clip"


class Job(BaseModel):
    id: str
    project_id: str | None
    type: JobType
    status: JobStatus
    progress: float
    current_step: str | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

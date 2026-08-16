from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import require_local_token
from app.core.youtube_download import VideoInfo, fetch_video_info
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_download_youtube_job

router = APIRouter(prefix="/youtube", tags=["youtube"], dependencies=[Depends(require_local_token)])


class VideoInfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format: Literal["video", "audio"] = "video"
    resolution: int | None = None  # required when format == "video"
    output_folder: str


@router.post("/info", response_model=VideoInfo)
def get_video_info(request: VideoInfoRequest) -> VideoInfo:
    try:
        return fetch_video_info(request.url)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user as a plain message
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/download", response_model=Job)
def download_video(request: DownloadRequest) -> Job:
    if request.format == "video" and request.resolution is None:
        raise HTTPException(status_code=400, detail="resolution is required when format='video'")

    job = job_manager.create(JobType.DOWNLOAD_YOUTUBE_VIDEO)
    thread = threading.Thread(
        target=run_download_youtube_job,
        args=(job.id, request.url, request.format, request.resolution, request.output_folder),
        daemon=True,
    )
    thread.start()
    return job

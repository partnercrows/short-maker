from __future__ import annotations

from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig


class AnalyzeRequest(BaseModel):
    provider: ProviderConfig
    num_clips: int | None = None  # None = let the AI decide how many clips to make
    use_gpu: bool = False  # GPU-accelerated Whisper transcription, if the device supports it


class GenerateClipRequest(BaseModel):
    include_subtitle: bool = False
    output_folder: str | None = None  # if set, the finished clip (+ subtitle) is also copied here


class ProjectCreate(BaseModel):
    name: str
    source_video_path: str
    source_duration: float | None = None
    source_resolution: str | None = None


class Project(BaseModel):
    id: str
    name: str
    source_video_path: str
    source_duration: float | None
    source_resolution: str | None
    status: str
    created_at: str
    updated_at: str


class Clip(BaseModel):
    id: str
    project_id: str
    start_time: float
    end_time: float
    duration: float
    score: float | None
    analysis_json: str | None
    transcript_json: str | None
    video_path: str | None
    subtitle_path: str | None
    subtitle_json_path: str | None = None
    intro_json_path: str | None = None
    status: str
    created_at: str
    updated_at: str


class SocialKit(BaseModel):
    id: str
    clip_id: str
    platform: str
    titles_json: str | None
    description: str | None
    hashtags: str | None
    thumbnail_idea: str | None
    thumbnail_prompt: str | None
    created_at: str
    updated_at: str


class AIProviderCreate(BaseModel):
    name: str
    provider_type: str
    base_url: str | None = None
    model: str | None = None


class AIProvider(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str | None
    model: str | None
    enabled: bool
    created_at: str
    updated_at: str

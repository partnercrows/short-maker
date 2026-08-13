from __future__ import annotations

from pydantic import BaseModel

from app.pipeline.common.face_detector import FaceBox


class SpeakerSegment(BaseModel):
    """One PRD S11 output segment: `{start, end, speaker_id, confidence}`."""

    start: float
    end: float
    speaker_id: str
    confidence: float


class TrackSample(BaseModel):
    timestamp: float
    box: FaceBox


class ActiveSpeakerResult(BaseModel):
    available: bool
    reason: str | None = None
    segments: list[SpeakerSegment] = []
    # Per-track face position over time. Not part of the PRD S11 public JSON
    # shape (segments is) -- reframe consumes this to build crop windows.
    track_trajectories: dict[str, list[TrackSample]] = {}

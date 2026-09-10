from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ReframeMode(StrEnum):
    CENTER_CROP = "center_crop"
    FACE_TRACKING = "face_tracking"
    ACTIVE_SPEAKER = "active_speaker"
    ACTIVE_SPEAKER_SMOOTH = "active_speaker_smooth"
    AUTO = "auto"
    # Internal-only fallback rung (PRD S14) — never user-selectable, only
    # reached via the AUTO/ACTIVE_SPEAKER/FACE_TRACKING fallback chains.
    PERSON_DETECTION = "person_detection"
    # Recipe Clipper's own strategy: follow the cooking action, keep faces
    # out of frame. Deliberately absent from the fallback chains in modes.py
    # -- Recipe Clipper resolves its framing directly, and AI Clipper must
    # never land here.
    FACELESS_COOKING = "faceless_cooking"


class CropWindow(BaseModel):
    """A crop rectangle in source-pixel coordinates at one point in time."""

    time: float
    x: int
    y: int
    width: int
    height: int


class ReframePlan(BaseModel):
    mode_used: ReframeMode
    fallback_reason: str | None = None
    windows: list[CropWindow]

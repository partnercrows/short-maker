"""Full-body/person-position fallback for when no face is detectable
(PRD S14). Stubbed until the MVP pipeline pass; see face_tracking.py for
the same rationale.
"""

from __future__ import annotations

from app.pipeline.reframe.models import CropWindow


class PersonDetector:
    def is_available(self) -> bool:
        return False

    def unavailable_reason(self) -> str:
        return "Person detection not yet implemented."

    def build_windows(self, video_path: str, target_width: int, target_height: int) -> list[CropWindow]:
        raise NotImplementedError

"""Face detection stage for Active Speaker (PRD S11).

Wraps the shared YuNet detector (see app.pipeline.common.face_detector for
why YuNet instead of MediaPipe). Real detection has landed; `is_available`
now reflects whether the model file actually loaded, not a hardcoded stub.
"""

from __future__ import annotations

import numpy as np

from app.pipeline.common.face_detector import FaceBox, YuNetFaceDetector


class ActiveSpeakerDetector:
    def __init__(self) -> None:
        self._detector: YuNetFaceDetector | None = None
        self._error: str | None = None
        try:
            self._detector = YuNetFaceDetector()
        except FileNotFoundError as exc:
            self._error = str(exc)

    def is_available(self) -> bool:
        return self._detector is not None

    def unavailable_reason(self) -> str:
        return self._error or "Face detector model not loaded."

    def detect(self, frame_bgr: np.ndarray) -> list[FaceBox]:
        if self._detector is None:
            raise RuntimeError(self.unavailable_reason())
        return self._detector.detect(frame_bgr)

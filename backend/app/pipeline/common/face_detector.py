"""Shared local face detector used by both `active_speaker/` and
`reframe/face_tracking.py` (PRD S14 fallback rungs share the same
detection primitive).

Uses OpenCV's bundled YuNet DNN detector rather than MediaPipe: an earlier
attempt at MediaPipe's Face Landmarker returned zero detections on this
Windows box across two mediapipe versions and a clean venv, despite a
verified-present face in every test image (confirmed via Haar cascade) —
a platform-specific failure, not a code bug. YuNet is the face detector
already validated via the clipforge audit (bundled there as an MIT
OpenCV-Zoo asset, see docs/THIRD_PARTY_NOTICES.md) and works reliably
here. It gives a bounding box + score per face; it does not give the
dense lip landmarks MediaPipe would have, which is why the active-speaker
scorer (`active_speaker/scorer`) uses mouth-region pixel motion energy
instead of a lip-landmark distance.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"


class FaceBox(BaseModel):
    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def iou(self, other: "FaceBox") -> float:
        ax1, ay1, ax2, ay2 = self.x, self.y, self.x + self.width, self.y + self.height
        bx1, by1, bx2, by2 = other.x, other.y, other.x + other.width, other.y + other.height
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        intersection = (ix2 - ix1) * (iy2 - iy1)
        union = self.width * self.height + other.width * other.height - intersection
        return intersection / union if union > 0 else 0.0


class YuNetFaceDetector:
    def __init__(self, score_threshold: float = 0.7, nms_threshold: float = 0.3, top_k: int = 20) -> None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"YuNet model not found at {MODEL_PATH}")
        self._model_path = str(MODEL_PATH)
        self._score_threshold = score_threshold
        self._nms_threshold = nms_threshold
        self._top_k = top_k
        self._detector: cv2.FaceDetectorYN | None = None
        self._input_size: tuple[int, int] | None = None

    def _ensure_detector(self, width: int, height: int) -> cv2.FaceDetectorYN:
        if self._detector is None or self._input_size != (width, height):
            self._detector = cv2.FaceDetectorYN_create(
                self._model_path, "", (width, height), self._score_threshold, self._nms_threshold, self._top_k
            )
            self._input_size = (width, height)
        return self._detector

    def detect(self, frame_bgr: np.ndarray) -> list[FaceBox]:
        height, width = frame_bgr.shape[:2]
        detector = self._ensure_detector(width, height)
        _, faces = detector.detect(frame_bgr)
        if faces is None:
            return []
        boxes = []
        for face in faces:
            x, y, w, h = face[:4]
            boxes.append(FaceBox(x=max(0, int(x)), y=max(0, int(y)), width=int(w), height=int(h), score=float(face[-1])))
        return boxes

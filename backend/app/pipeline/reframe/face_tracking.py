"""Per-frame face position tracking, used when Active Speaker is
unavailable (PRD S12/S14). Reuses the same YuNet detector + IOU tracker
as active_speaker (see app.pipeline.common), minus the mouth-motion
scoring -- this rung just follows whichever face is largest/most
prominent, on the assumption that's usually the person the camera should
be on when we can't tell who's talking.
"""

from __future__ import annotations

import cv2

from app.pipeline.common.face_detector import YuNetFaceDetector
from app.pipeline.common.tracker import IouTracker
from app.pipeline.reframe.center_crop import build_static_window, target_crop_size
from app.pipeline.reframe.models import CropWindow
from app.pipeline.reframe.smoothing import smooth_positions


class FaceTracker:
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

    def build_windows(
        self, video_path: str, target_width: int, target_height: int, frame_stride: int = 2
    ) -> list[CropWindow]:
        if self._detector is None:
            raise RuntimeError(self.unavailable_reason())

        capture = cv2.VideoCapture(video_path)
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        tracker = IouTracker()

        samples: list[tuple[float, float]] = []  # (timestamp, center_x)
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % frame_stride != 0:
                frame_index += 1
                continue
            boxes = self._detector.detect(frame)
            active = tracker.update(frame_index, boxes)
            if active:
                largest = max(active.values(), key=lambda b: b.width * b.height)
                samples.append((frame_index / fps, largest.center[0]))
            frame_index += 1
        capture.release()

        if not samples:
            return [build_static_window(source_width, source_height, target_width, target_height)]

        crop_width, crop_height = target_crop_size(source_width, source_height, target_width, target_height)
        smoothed_x = smooth_positions([x for _, x in samples])
        windows = []
        for (timestamp, _), center_x in zip(samples, smoothed_x):
            x = int(max(0, min(source_width - crop_width, center_x - crop_width / 2)))
            windows.append(CropWindow(time=timestamp, x=x, y=0, width=crop_width, height=crop_height))
        return windows

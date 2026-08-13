"""Speaker-to-face association across frames (PRD S11).

A thin wrapper over the shared IOU tracker (app.pipeline.common.tracker) --
active_speaker doesn't need anything beyond persistent track IDs with an
occlusion grace period; the mouth-motion scoring itself lives in
`active_speaker.scorer`.
"""

from __future__ import annotations

from app.pipeline.common.face_detector import FaceBox
from app.pipeline.common.tracker import IouTracker


class SpeakerTracker:
    def __init__(self, iou_threshold: float = 0.2, max_missed_frames: int = 20) -> None:
        self._tracker = IouTracker(iou_threshold=iou_threshold, max_missed_frames=max_missed_frames)

    def update(self, frame_index: int, boxes: list[FaceBox]) -> dict[int, FaceBox]:
        return self._tracker.update(frame_index, boxes)

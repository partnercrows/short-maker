"""Greedy IOU tracker: assigns persistent track IDs to per-frame face
detections. The grace period (frames a track survives with no matching
detection before being dropped) is what exercises PRD scenario 6
(speaker partially occluded) — a brief occlusion no longer breaks the
speaker_id continuity that reframe/active_speaker rely on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipeline.common.face_detector import FaceBox


@dataclass
class Track:
    track_id: int
    box: FaceBox
    missed_frames: int = 0
    history: list[tuple[int, FaceBox]] = field(default_factory=list)


class IouTracker:
    def __init__(self, iou_threshold: float = 0.3, max_missed_frames: int = 8) -> None:
        self._iou_threshold = iou_threshold
        self._max_missed_frames = max_missed_frames
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, frame_index: int, boxes: list[FaceBox]) -> dict[int, FaceBox]:
        unmatched_boxes = list(boxes)
        matched_track_ids: set[int] = set()

        for track in sorted(self._tracks.values(), key=lambda t: -t.box.score):
            if not unmatched_boxes:
                break
            best_iou, best_box = 0.0, None
            for box in unmatched_boxes:
                iou = track.box.iou(box)
                if iou > best_iou:
                    best_iou, best_box = iou, box
            if best_box is not None and best_iou >= self._iou_threshold:
                track.box = best_box
                track.missed_frames = 0
                track.history.append((frame_index, best_box))
                matched_track_ids.add(track.track_id)
                unmatched_boxes.remove(best_box)

        for track in self._tracks.values():
            if track.track_id not in matched_track_ids:
                track.missed_frames += 1

        for box in unmatched_boxes:
            track = Track(track_id=self._next_id, box=box, history=[(frame_index, box)])
            self._tracks[self._next_id] = track
            self._next_id += 1

        self._tracks = {tid: t for tid, t in self._tracks.items() if t.missed_frames <= self._max_missed_frames}

        return {tid: t.box for tid, t in self._tracks.items() if t.missed_frames == 0}

    @property
    def tracks(self) -> dict[int, Track]:
        return self._tracks

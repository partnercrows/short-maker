"""Orchestrates detector -> tracker -> scorer over a whole video (PRD S11-S12).

Never raises for expected "nothing to detect" outcomes: an unavailable or
empty result is normal and the reframe fallback chain
(`app.pipeline.reframe.modes`) is what actually decides what to do about
it, per the "must never be a single point of failure" requirement (S12).
"""

from __future__ import annotations

import cv2

from app.pipeline.active_speaker.detector import ActiveSpeakerDetector
from app.pipeline.active_speaker.models import ActiveSpeakerResult, TrackSample
from app.pipeline.active_speaker.scorer import decide_active_speaker, merge_into_segments, motion_energy, mouth_region
from app.pipeline.active_speaker.tracker import SpeakerTracker
from app.pipeline.common.face_detector import FaceBox


MIN_FACE_SIZE_PX = 40


def run(video_path: str, frame_stride: int = 2) -> ActiveSpeakerResult:
    detector = ActiveSpeakerDetector()
    if not detector.is_available():
        return ActiveSpeakerResult(available=False, reason=detector.unavailable_reason())

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        return ActiveSpeakerResult(available=False, reason=f"Could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    tracker = SpeakerTracker()

    frame_decisions: list[tuple[float, int | None, float]] = []
    trajectories: dict[int, list[TrackSample]] = {}
    prev_mouth_crops: dict[int, "cv2.typing.MatLike"] = {}

    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % frame_stride != 0:
            frame_index += 1
            continue
        timestamp = frame_index / fps

        boxes = [b for b in detector.detect(frame) if b.width >= MIN_FACE_SIZE_PX and b.height >= MIN_FACE_SIZE_PX]
        active_tracks = tracker.update(frame_index, boxes)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        energies: dict[int, float] = {}
        current_mouth_crops: dict[int, "cv2.typing.MatLike"] = {}

        for track_id, box in active_tracks.items():
            trajectories.setdefault(track_id, []).append(TrackSample(timestamp=timestamp, box=box))

            mx, my, mw, mh = mouth_region(box)
            crop = gray[my : my + mh, mx : mx + mw]
            current_mouth_crops[track_id] = crop
            if track_id in prev_mouth_crops:
                energies[track_id] = motion_energy(prev_mouth_crops[track_id], crop)

        prev_mouth_crops = current_mouth_crops
        speaker_id, confidence = decide_active_speaker(energies)
        frame_decisions.append((timestamp, speaker_id, confidence))
        frame_index += 1

    capture.release()

    segments = merge_into_segments(frame_decisions)
    track_trajectories = {f"face_{track_id}": samples for track_id, samples in trajectories.items()}

    if not segments:
        return ActiveSpeakerResult(
            available=False, reason="No confident active-speaker segments found.", track_trajectories=track_trajectories
        )

    return ActiveSpeakerResult(available=True, segments=segments, track_trajectories=track_trajectories)

"""Reframe mode resolution + fallback chain (PRD S12/S14).

`ReframeMode.PERSON_DETECTION` doesn't exist as a user-selectable mode in
the PRD's UI (S14 only lists Center Crop / Face Tracking / Active Speaker
/ Active Speaker + Smooth / Auto) — person detection is purely an
internal fallback rung between Face Tracking and Center Crop, reached via
`FaceTracker`/`PersonDetector` unavailability, never chosen directly.

This resolves *which* method will run and produces its crop windows; it
never fails; Center Crop is a pure-geometry floor with no external
dependency, so the chain always terminates successfully.
"""

from __future__ import annotations

from statistics import median

from app.pipeline.active_speaker import pipeline as active_speaker_pipeline
from app.pipeline.active_speaker.models import ActiveSpeakerResult
from app.pipeline.reframe.center_crop import build_static_window, target_crop_size
from app.pipeline.reframe.face_tracking import FaceTracker
from app.pipeline.reframe.models import CropWindow, ReframeMode, ReframePlan
from app.pipeline.reframe.person_detection import PersonDetector
from app.pipeline.reframe.smoothing import segment_hold_and_pan

_CHAINS: dict[ReframeMode, list[ReframeMode]] = {
    ReframeMode.AUTO: [
        ReframeMode.ACTIVE_SPEAKER,
        ReframeMode.FACE_TRACKING,
        ReframeMode.PERSON_DETECTION,  # internal-only rung, see module docstring
        ReframeMode.CENTER_CROP,
    ],
    ReframeMode.ACTIVE_SPEAKER_SMOOTH: [
        ReframeMode.ACTIVE_SPEAKER,
        ReframeMode.FACE_TRACKING,
        ReframeMode.PERSON_DETECTION,
        ReframeMode.CENTER_CROP,
    ],
    ReframeMode.ACTIVE_SPEAKER: [
        ReframeMode.ACTIVE_SPEAKER,
        ReframeMode.FACE_TRACKING,
        ReframeMode.PERSON_DETECTION,
        ReframeMode.CENTER_CROP,
    ],
    ReframeMode.FACE_TRACKING: [
        ReframeMode.FACE_TRACKING,
        ReframeMode.PERSON_DETECTION,
        ReframeMode.CENTER_CROP,
    ],
    ReframeMode.CENTER_CROP: [ReframeMode.CENTER_CROP],
}


def resolve(
    *,
    video_path: str,
    requested_mode: ReframeMode,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> ReframePlan:
    chain = _CHAINS[requested_mode]
    fallback_reason: str | None = None

    for step in chain:
        # Every rung except Center Crop touches a model/video/subprocess and can
        # fail in ways its own code doesn't anticipate (corrupt file, missing
        # model, ...). Catching broadly here is what actually delivers the PRD
        # S12 guarantee -- a bug in one rung must fall through, not propagate.
        try:
            if step == ReframeMode.ACTIVE_SPEAKER:
                result = active_speaker_pipeline.run(video_path)
                if result.available:
                    windows = _windows_from_active_speaker(
                        result, source_width, source_height, target_width, target_height
                    )
                    return ReframePlan(mode_used=requested_mode, fallback_reason=fallback_reason, windows=windows)
                fallback_reason = result.reason
                continue

            if step == ReframeMode.FACE_TRACKING:
                tracker = FaceTracker()
                if tracker.is_available():
                    windows = tracker.build_windows(video_path, target_width, target_height)
                    if windows:
                        return ReframePlan(mode_used=step, fallback_reason=fallback_reason, windows=windows)
                    fallback_reason = "Face tracking found no usable frames."
                    continue
                fallback_reason = tracker.unavailable_reason()
                continue

            if step == ReframeMode.PERSON_DETECTION:
                detector = PersonDetector()
                if detector.is_available():
                    windows = detector.build_windows(video_path, target_width, target_height)
                    return ReframePlan(mode_used=step, fallback_reason=fallback_reason, windows=windows)
                fallback_reason = detector.unavailable_reason()
                continue
        except Exception as exc:  # noqa: BLE001 -- intentional: see comment above
            fallback_reason = f"{step.value} failed: {exc}"
            continue

        if step == ReframeMode.CENTER_CROP:
            window = build_static_window(source_width, source_height, target_width, target_height)
            return ReframePlan(mode_used=step, fallback_reason=fallback_reason, windows=[window])

    raise AssertionError("Fallback chains must always terminate in CENTER_CROP")


def _windows_from_active_speaker(
    result: ActiveSpeakerResult, source_width: int, source_height: int, target_width: int, target_height: int
) -> list[CropWindow]:
    """Follows whichever speaker `result.segments` says is active.

    One target x-position per segment (median of that speaker's face
    trajectory across it, which cancels ordinary detection jitter), held
    steady for the segment's duration with a single short eased pan at
    each switch -- per PRD S13's own diagram (position A -> smooth
    transition -> position B), not continuous per-frame tracking, which
    reads as a hesitant, jittery cameraman instead of a deliberate pan.
    """
    segments: list[tuple[float, float, float]] = []
    for segment in sorted(result.segments, key=lambda s: s.start):
        trajectory = result.track_trajectories.get(segment.speaker_id, [])
        xs = [sample.box.center[0] for sample in trajectory if segment.start <= sample.timestamp <= segment.end]
        if xs:
            segments.append((segment.start, segment.end, median(xs)))

    crop_width, crop_height = target_crop_size(source_width, source_height, target_width, target_height)
    keyframes = segment_hold_and_pan(segments)
    windows = []
    for timestamp, center_x in keyframes:
        x = int(max(0, min(source_width - crop_width, center_x - crop_width / 2)))
        windows.append(CropWindow(time=timestamp, x=x, y=0, width=crop_width, height=crop_height))
    return windows

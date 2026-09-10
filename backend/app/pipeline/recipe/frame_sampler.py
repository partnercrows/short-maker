"""Finding *which* frames are worth showing the AI (PRD S6, S46).

A cooking video can run two hours, and sending it all to a vision model is
neither affordable nor necessary. But a plain fixed grid is worse than it
looks: at an affordable rate it spends half its budget on thirty minutes of
identical simmering and still misses the three-second moment the sauce goes
in -- and that moment is the whole point of the feature.

So: decode once into a cheap downscaled strip, work out locally (no AI, no
new dependency) where the video actually *changes*, and spend the frame
budget there -- with a floor of coverage across the whole timeline, because
the plating and the final dish live at the very end and must never be
invisible to the model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np

from app.core.ffmpeg_utils import extract_frame_sequence
from app.pipeline.recipe.models import VisualSegment

# One decode, this many probe frames at most, whatever the source length --
# the interval stretches instead. 1800 frames is ~60 MB of 512px JPEG.
PROBE_TARGET_FRAMES = 1800
PROBE_MIN_INTERVAL = 1.0
PROBE_WIDTH = 512

_ANALYSIS_WIDTH = 64  # motion is computed on a thumbnail; detail would only add noise
_ANALYSIS_HEIGHT = 36
_MIN_SHOT_SECONDS = 1.5
_MAX_SHOT_SECONDS = 20.0
_COVERAGE_BUCKETS = 24
_MIN_PER_BUCKET = 2


def probe_interval_for(duration_seconds: float) -> float:
    """Seconds between probe frames: 1s for a half-hour video, 4s for two hours."""
    if duration_seconds <= 0:
        return PROBE_MIN_INTERVAL
    return max(PROBE_MIN_INTERVAL, duration_seconds / PROBE_TARGET_FRAMES)


def keyframe_budget(duration_seconds: float) -> int:
    """How many frames we are willing to send to the vision model.

    This is the cost knob for the whole feature: at ~258 image tokens each,
    even the largest budget is a fraction of a cent on a flash-class model,
    while being enough frames to see every step of a long recipe.
    """
    minutes = duration_seconds / 60.0
    if minutes <= 20:
        return 72
    if minutes <= 45:
        return 108
    if minutes <= 90:
        return 144
    return 180


def extract_probe_frames(video_path: str, output_dir: Path, duration_seconds: float) -> tuple[list[Path], float]:
    """One ffmpeg decode of the whole video into a downscaled JPEG strip."""
    interval = probe_interval_for(duration_seconds)
    frames = extract_frame_sequence(video_path, str(output_dir), interval_seconds=interval, width=PROBE_WIDTH)
    return frames, interval


def _frame_features(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    small = cv2.resize(image, (_ANALYSIS_WIDTH, _ANALYSIS_HEIGHT), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    histogram = cv2.calcHist([small], [0, 1, 2], None, [8, 8, 8], [0, 256] * 3)
    cv2.normalize(histogram, histogram)
    return gray, histogram.flatten()


def segment_shots(frames: list[Path], interval: float) -> list[VisualSegment]:
    """Cut the probe strip into shots, and measure how much each one moves.

    A shot boundary is a colour-histogram jump; motion within a shot is the
    mean absolute frame difference. Both are cheap enough to run over the
    whole strip, and together they answer the two questions the selector
    needs: where does the video change, and where is something happening.
    """
    grays: list[np.ndarray] = []
    histograms: list[np.ndarray] = []
    usable: list[Path] = []
    for path in frames:
        features = _frame_features(path)
        if features is None:
            continue
        grays.append(features[0])
        histograms.append(features[1])
        usable.append(path)

    if not usable:
        return []

    motion = [0.0]
    cut_distance = [0.0]
    for i in range(1, len(usable)):
        motion.append(float(np.mean(cv2.absdiff(grays[i], grays[i - 1]))))
        correlation = float(cv2.compareHist(histograms[i], histograms[i - 1], cv2.HISTCMP_CORREL))
        cut_distance.append(1.0 - correlation)

    threshold = max(0.25, float(np.mean(cut_distance) + 2.5 * np.std(cut_distance)))
    boundaries = [0] + [i for i in range(1, len(usable)) if cut_distance[i] > threshold] + [len(usable)]

    segments: list[VisualSegment] = []
    for start_index, end_index in zip(boundaries, boundaries[1:]):
        if end_index <= start_index:
            continue
        window = motion[start_index:end_index]
        peak_offset = int(np.argmax(window)) if window else 0
        segments.append(
            VisualSegment(
                index=len(segments),
                start=start_index * interval,
                end=end_index * interval,
                peak_time=(start_index + peak_offset) * interval,
                motion=float(np.mean(window)) if window else 0.0,
                frame_path=usable[start_index + peak_offset],
            )
        )

    return _split_long_shots(_merge_short_shots(segments, interval), interval)


def _merge_short_shots(segments: list[VisualSegment], interval: float) -> list[VisualSegment]:
    """A flicker of noise is not a shot. Fold anything under 1.5s into its neighbour."""
    merged: list[VisualSegment] = []
    for segment in segments:
        if merged and segment.duration < max(_MIN_SHOT_SECONDS, interval):
            previous = merged[-1]
            keep_new_peak = segment.motion > previous.motion
            merged[-1] = previous.model_copy(
                update={
                    "end": segment.end,
                    "motion": max(previous.motion, segment.motion),
                    "peak_time": segment.peak_time if keep_new_peak else previous.peak_time,
                    "frame_path": segment.frame_path if keep_new_peak else previous.frame_path,
                }
            )
            continue
        merged.append(segment)
    return [segment.model_copy(update={"index": i}) for i, segment in enumerate(merged)]


def _split_long_shots(segments: list[VisualSegment], interval: float) -> list[VisualSegment]:
    """A single locked-off shot can hold the whole cook. Split it so the
    selector can pick several distinct moments out of one camera setup."""
    split: list[VisualSegment] = []
    for segment in segments:
        if segment.duration <= _MAX_SHOT_SECONDS:
            split.append(segment)
            continue
        pieces = max(2, int(math.ceil(segment.duration / _MAX_SHOT_SECONDS)))
        piece_duration = segment.duration / pieces
        for piece in range(pieces):
            start = segment.start + piece * piece_duration
            split.append(
                segment.model_copy(
                    update={
                        "start": start,
                        "end": start + piece_duration,
                        "peak_time": min(start + piece_duration / 2, max(start, segment.end - interval)),
                    }
                )
            )
    return [segment.model_copy(update={"index": i}) for i, segment in enumerate(split)]


def select_keyframes(segments: list[VisualSegment], duration_seconds: float, budget: int | None = None) -> list[VisualSegment]:
    """Spend the frame budget on the shots most likely to be a cooking step.

    Score favours movement and length, but coverage is enforced first: every
    part of the timeline that has footage contributes at least a couple of
    frames. Without that a video with a busy first ten minutes would send
    nothing at all from the plating at 54:00, and PRD S11/S12 make the late
    plating and final dish mandatory.
    """
    if not segments:
        return []
    budget = budget or keyframe_budget(duration_seconds)
    if len(segments) <= budget:
        return sorted(segments, key=lambda s: s.start)

    ranked = sorted(segments, key=_score, reverse=True)
    chosen: dict[int, VisualSegment] = {}

    # 1. Coverage floor, bucket by bucket.
    span = max(duration_seconds, segments[-1].end, 1.0)
    for bucket in range(_COVERAGE_BUCKETS):
        low = span * bucket / _COVERAGE_BUCKETS
        high = span * (bucket + 1) / _COVERAGE_BUCKETS
        in_bucket = [s for s in ranked if low <= s.peak_time < high]
        for segment in in_bucket[:_MIN_PER_BUCKET]:
            chosen[segment.index] = segment

    # 2. The hook and the final dish live at the very edges (PRD S11).
    for segment in segments:
        if segment.peak_time <= span * 0.02 or segment.peak_time >= span * 0.97:
            chosen[segment.index] = segment

    # 3. Spend what is left on the highest-scoring shots.
    for segment in ranked:
        if len(chosen) >= budget:
            break
        chosen[segment.index] = segment

    return sorted(chosen.values(), key=lambda s: s.start)[:budget]


def _score(segment: VisualSegment) -> float:
    return segment.motion * math.log1p(segment.duration)


def save_frame_index(path: Path, segments: list[VisualSegment], interval: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "interval": interval,
        "segments": [json.loads(segment.model_dump_json()) for segment in segments],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

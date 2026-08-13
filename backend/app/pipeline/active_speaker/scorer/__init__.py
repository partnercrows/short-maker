"""Active-speaker decision from mouth-motion energy (PRD S11-S12).

No neural ASD model is used here (see docs/THIRD_PARTY_NOTICES.md for why
Light-ASD/LR-ASD were deferred). Instead: per tracked face, crop the lower
third of its bounding box (an approximate mouth region) and measure
frame-to-frame grayscale pixel-difference energy. The track with the
most mouth motion in a given moment is deemed the active speaker, gated
by a floor (near-zero motion means "nobody is clearly talking", not "pick
someone anyway") and a margin-based confidence between the top two
tracks.

This is a real, working heuristic — not a stub — but it is approximate:
it can be fooled by non-speech mouth movement (chewing, laughing) and
gives low confidence when two people talk over each other. Both
limitations are recorded in docs/ACTIVE_SPEAKER_SPIKE.md.
"""

from __future__ import annotations

import numpy as np

from app.pipeline.active_speaker.models import SpeakerSegment
from app.pipeline.common.face_detector import FaceBox

MOTION_FLOOR = 2.0  # mean abs grayscale delta below this = "no one is talking"
MIN_SEGMENT_DURATION = 0.3  # seconds; shorter blips get merged into neighbors


def mouth_region(box: FaceBox) -> tuple[int, int, int, int]:
    """Lower third of the face box, inset slightly so it stays on the
    mouth rather than the chin/jawline edge."""
    x = box.x + int(box.width * 0.2)
    y = box.y + int(box.height * 0.62)
    w = int(box.width * 0.6)
    h = int(box.height * 0.3)
    return x, y, max(w, 1), max(h, 1)


def motion_energy(prev_gray_crop: np.ndarray, curr_gray_crop: np.ndarray) -> float:
    if prev_gray_crop.shape != curr_gray_crop.shape or prev_gray_crop.size == 0:
        return 0.0
    return float(np.mean(np.abs(curr_gray_crop.astype(np.int16) - prev_gray_crop.astype(np.int16))))


def decide_active_speaker(energies: dict[int, float]) -> tuple[int | None, float]:
    if not energies:
        return None, 0.0
    ranked = sorted(energies.items(), key=lambda kv: -kv[1])
    top_id, top_energy = ranked[0]
    if top_energy < MOTION_FLOOR:
        return None, 0.0
    second_energy = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = (top_energy - second_energy) / (top_energy + second_energy + 1e-6)
    confidence = 0.5 + 0.5 * confidence  # map margin ratio [0,1] onto confidence [0.5,1.0]
    return top_id, confidence


def merge_into_segments(
    frame_decisions: list[tuple[float, int | None, float]],
    min_segment_duration: float = MIN_SEGMENT_DURATION,
) -> list[SpeakerSegment]:
    """Collapses consecutive same-speaker frame decisions into segments,
    dropping/merging blips shorter than min_segment_duration."""
    raw_segments: list[list] = []  # [start, end, speaker_id, [confidences]]
    for timestamp, speaker_id, confidence in frame_decisions:
        if speaker_id is None:
            continue
        if raw_segments and raw_segments[-1][2] == speaker_id and timestamp - raw_segments[-1][1] < 0.5:
            raw_segments[-1][1] = timestamp
            raw_segments[-1][3].append(confidence)
        else:
            raw_segments.append([timestamp, timestamp, speaker_id, [confidence]])

    segments = [
        SpeakerSegment(start=start, end=end, speaker_id=f"face_{speaker_id}", confidence=sum(confs) / len(confs))
        for start, end, speaker_id, confs in raw_segments
        if end - start >= min_segment_duration
    ]
    return segments

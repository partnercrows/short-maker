import numpy as np

from app.pipeline.active_speaker.scorer import decide_active_speaker, merge_into_segments, motion_energy, mouth_region
from app.pipeline.common.face_detector import FaceBox


def test_mouth_region_is_lower_third_of_box():
    box = FaceBox(x=100, y=200, width=80, height=100, score=0.9)
    x, y, w, h = mouth_region(box)
    assert x > box.x and x + w < box.x + box.width  # inset horizontally
    assert y > box.y + box.height // 2  # in the lower half of the face


def test_motion_energy_zero_for_identical_crops():
    crop = np.full((20, 20), 128, dtype=np.uint8)
    assert motion_energy(crop, crop) == 0.0


def test_motion_energy_positive_for_changed_crop():
    prev = np.full((20, 20), 100, dtype=np.uint8)
    curr = np.full((20, 20), 150, dtype=np.uint8)
    assert motion_energy(prev, curr) == 50.0


def test_decide_picks_highest_energy_above_floor():
    speaker_id, confidence = decide_active_speaker({1: 10.0, 2: 3.0})
    assert speaker_id == 1
    assert confidence > 0.5


def test_decide_returns_none_when_everything_is_still():
    speaker_id, confidence = decide_active_speaker({1: 0.5, 2: 0.3})
    assert speaker_id is None
    assert confidence == 0.0


def test_decide_returns_none_for_empty_input():
    assert decide_active_speaker({}) == (None, 0.0)


def test_merge_collapses_consecutive_same_speaker_frames():
    decisions = [(0.0, 1, 0.9), (0.1, 1, 0.8), (0.2, 1, 0.85)]
    segments = merge_into_segments(decisions, min_segment_duration=0.1)
    assert len(segments) == 1
    assert segments[0].speaker_id == "face_1"
    assert segments[0].start == 0.0
    assert segments[0].end == 0.2


def test_merge_drops_blips_shorter_than_minimum_duration():
    decisions = [(0.0, 1, 0.9)]  # a single instantaneous frame, zero duration
    segments = merge_into_segments(decisions, min_segment_duration=0.1)
    assert segments == []


def test_merge_splits_on_speaker_change():
    decisions = [(0.0, 1, 0.9), (0.3, 1, 0.9), (0.6, 2, 0.9), (0.9, 2, 0.9)]
    segments = merge_into_segments(decisions, min_segment_duration=0.1)
    assert [s.speaker_id for s in segments] == ["face_1", "face_2"]

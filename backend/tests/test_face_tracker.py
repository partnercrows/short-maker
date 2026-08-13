from app.pipeline.common.face_detector import FaceBox
from app.pipeline.common.tracker import IouTracker


def _box(x: int, y: int = 100, w: int = 80, h: int = 80, score: float = 0.9) -> FaceBox:
    return FaceBox(x=x, y=y, width=w, height=h, score=score)


def test_matching_box_keeps_same_track_id():
    tracker = IouTracker()
    active = tracker.update(0, [_box(100)])
    first_id = next(iter(active))

    active = tracker.update(1, [_box(105)])  # small shift, still overlaps a lot
    assert list(active.keys()) == [first_id]


def test_track_survives_a_brief_occlusion_gap():
    tracker = IouTracker(max_missed_frames=5)
    active = tracker.update(0, [_box(100)])
    track_id = next(iter(active))

    for frame in range(1, 4):  # 3 missed frames, within the grace period
        active = tracker.update(frame, [])
        assert active == {}

    active = tracker.update(4, [_box(102)])  # reappears close to where it was
    assert list(active.keys()) == [track_id]


def test_track_dropped_after_grace_period_exceeded():
    tracker = IouTracker(max_missed_frames=2)
    tracker.update(0, [_box(100)])

    for frame in range(1, 5):
        tracker.update(frame, [])

    assert tracker.tracks == {}


def test_unrelated_box_gets_a_new_track_id():
    tracker = IouTracker()
    active = tracker.update(0, [_box(100)])
    first_id = next(iter(active))

    active = tracker.update(1, [_box(100), _box(500)])  # original face + a new, distant one
    assert len(active) == 2
    assert first_id in active

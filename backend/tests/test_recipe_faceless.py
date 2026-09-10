from __future__ import annotations

from app.pipeline.common.face_detector import FaceBox
from app.pipeline.recipe import face_check, faceless_reframe
from app.pipeline.recipe.faceless_reframe import FacelessSample, FacelessScan
from app.pipeline.reframe.models import ReframeMode

SOURCE_WIDTH = 1920
SOURCE_HEIGHT = 1080
TARGET_WIDTH = 720
TARGET_HEIGHT = 1280


def _sample(time: float, hot_column: int | None, faces: list[FaceBox] | None = None) -> FacelessSample:
    """One scanned frame: motion concentrated in `hot_column`, if any."""
    columns = [0.0] * faceless_reframe.COLUMN_BINS
    rows = [0.0] * faceless_reframe.ROW_BINS
    if hot_column is not None:
        columns[hot_column] = 100.0
        rows[len(rows) // 2] = 100.0
    return FacelessSample(
        time=time,
        column_energy=columns,
        row_energy=rows,
        total_motion=0.2 if hot_column is not None else 0.0,
        faces=faces or [],
    )


def _scan(samples: list[FacelessSample]) -> FacelessScan:
    return FacelessScan(fps=30.0, source_width=SOURCE_WIDTH, source_height=SOURCE_HEIGHT, samples=samples)


def test_the_crop_follows_where_the_action_is():
    """PRD S16: board on the left means the framing moves left."""
    left = _scan([_sample(i / 10, hot_column=2) for i in range(20)])
    right = _scan([_sample(i / 10, hot_column=faceless_reframe.COLUMN_BINS - 3) for i in range(20)])

    left_plan = faceless_reframe.build_plan(left, TARGET_WIDTH, TARGET_HEIGHT)
    right_plan = faceless_reframe.build_plan(right, TARGET_WIDTH, TARGET_HEIGHT)

    assert left_plan.windows[0].x < right_plan.windows[0].x
    assert left_plan.mode_used is ReframeMode.FACELESS_COOKING


def test_a_still_shot_frames_centrally_rather_than_chasing_noise():
    """A plating shot with nothing moving should sit in the middle (PRD S16)."""
    scan = _scan([_sample(i / 10, hot_column=None) for i in range(10)])

    plan = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT)

    window = plan.windows[0]
    centre = (SOURCE_WIDTH - window.width) // 2
    assert abs(window.x - centre) <= faceless_reframe.POSITION_STEP


def test_the_crop_is_pushed_away_from_a_face_next_to_the_action():
    face = FaceBox(x=1500, y=100, width=220, height=260, score=0.9)
    samples = [_sample(i / 10, hot_column=faceless_reframe.COLUMN_BINS - 6, faces=[face]) for i in range(20)]

    with_face = faceless_reframe.build_plan(_scan(samples), TARGET_WIDTH, TARGET_HEIGHT)
    without_face = faceless_reframe.build_plan(
        _scan([_sample(i / 10, hot_column=faceless_reframe.COLUMN_BINS - 6) for i in range(20)]),
        TARGET_WIDTH,
        TARGET_HEIGHT,
    )

    assert with_face.windows[0].x < without_face.windows[0].x


def test_every_window_in_a_plan_keeps_the_same_crop_size():
    """render.interpolated_window only interpolates x/y -- a plan that changed
    crop size midway would snap."""
    scan = _scan([_sample(i / 10, hot_column=i % faceless_reframe.COLUMN_BINS) for i in range(30)])

    plan = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT)

    assert len({(w.width, w.height) for w in plan.windows}) == 1


def test_zooming_in_frees_the_vertical_axis():
    scan = _scan([_sample(i / 10, hot_column=10) for i in range(10)])

    normal = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT, zoom=1.0)
    zoomed = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT, zoom=1.5)

    assert normal.windows[0].height == SOURCE_HEIGHT  # 9:16 out of 16:9 keeps full height
    assert zoomed.windows[0].height < normal.windows[0].height


def test_a_static_plan_is_a_single_window():
    scan = _scan([_sample(i / 10, hot_column=i % 8) for i in range(20)])

    plan = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT, static=True)

    assert len(plan.windows) == 1


def test_validation_measures_how_much_face_lands_in_the_output():
    face = FaceBox(x=0, y=0, width=300, height=300, score=0.9)
    scan = _scan([_sample(i / 10, hot_column=1, faces=[face]) for i in range(10)])
    plan = faceless_reframe.build_plan(scan, TARGET_WIDTH, TARGET_HEIGHT, avoid_faces=False)

    worst, ratio = face_check.validate_plan(scan, plan)

    assert worst > face_check.FACE_CLEAN_OVERLAP
    assert ratio > 0


def test_a_clean_scene_reports_clean(monkeypatch):
    scan = _scan([_sample(i / 10, hot_column=4) for i in range(10)])
    monkeypatch.setattr(face_check, "scan", lambda *a, **k: scan)

    plan, check = face_check.resolve_faceless(
        video_path="scene.mp4", target_width=TARGET_WIDTH, target_height=TARGET_HEIGHT
    )

    assert check.status == "clean"
    assert check.strategy_used == "dynamic_crop"
    assert plan.windows


def test_an_unavoidable_face_is_flagged_rather_than_blurred(monkeypatch):
    """PRD S45: say so, offer the user a choice, and never blur."""
    everywhere = [
        FaceBox(x=0, y=0, width=SOURCE_WIDTH, height=SOURCE_HEIGHT, score=0.99),
    ]
    scan = _scan([_sample(i / 10, hot_column=10, faces=everywhere) for i in range(10)])
    monkeypatch.setattr(face_check, "scan", lambda *a, **k: scan)

    _plan, check = face_check.resolve_faceless(
        video_path="scene.mp4", target_width=TARGET_WIDTH, target_height=TARGET_HEIGHT
    )

    assert check.status == "warning"
    assert check.message and "could not be fully kept out" in check.message


def test_faceless_off_skips_face_avoidance_entirely(monkeypatch):
    seen = {}

    def fake_scan(video_path, *, frame_stride=3, detect_faces=True):
        seen["detect_faces"] = detect_faces
        return _scan([_sample(i / 10, hot_column=4) for i in range(5)])

    monkeypatch.setattr(face_check, "scan", fake_scan)

    _plan, check = face_check.resolve_faceless(
        video_path="scene.mp4", target_width=TARGET_WIDTH, target_height=TARGET_HEIGHT, faceless=False
    )

    assert seen["detect_faces"] is False
    assert check.status == "clean"


def test_center_fallback_is_a_single_centred_window():
    plan = face_check.center_fallback_plan(SOURCE_WIDTH, SOURCE_HEIGHT, TARGET_WIDTH, TARGET_HEIGHT)

    assert plan.mode_used is ReframeMode.CENTER_CROP
    assert len(plan.windows) == 1

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


# --- camera discipline (PRD S16) --------------------------------------------


def _moving_scan(columns: list[int], fps: float = 10.0) -> FacelessScan:
    """A scan whose action sits in `columns[i]` at each sampled moment."""
    return _scan([_sample(i / fps, hot_column=column) for i, column in enumerate(columns)])


def _x_positions(plan) -> list[int]:
    return [window.x for window in plan.windows]


def test_action_wobbling_side_to_side_does_not_move_the_camera():
    """The complaint that started this: hands crossing the frame and coming
    back made the crop drift left and right continuously, which is dizzying
    to watch even though each step was small."""
    # 12 seconds of it -- long past the point where the camera is allowed to
    # move at all, so this exercises the dwell rule rather than the
    # short-scene shortcut.
    wobble = ([4] * 5 + [44] * 5) * 12
    plan = faceless_reframe.build_plan(_moving_scan(wobble), TARGET_WIDTH, TARGET_HEIGHT)

    assert len(set(_x_positions(plan))) == 1  # one framing, held throughout


def test_a_short_scene_gets_one_framing_whatever_happens_in_it():
    """Most recipe scenes are a few seconds; moving inside one is never worth it."""
    plan = faceless_reframe.build_plan(_moving_scan([2, 8, 20, 34, 44]), TARGET_WIDTH, TARGET_HEIGHT)

    assert len(set(_x_positions(plan))) == 1


def test_the_camera_does_follow_action_that_genuinely_relocates():
    """Cook moves from the board on the left to the stove on the right and
    stays there -- that is worth following."""
    columns = [3] * 60 + [44] * 60  # 6s left, then 6s right, at 10 samples/s
    plan = faceless_reframe.build_plan(_moving_scan(columns), TARGET_WIDTH, TARGET_HEIGHT)

    xs = _x_positions(plan)
    assert len(set(xs)) > 1, "a real relocation should be followed"
    assert xs[-1] > xs[0], "and followed in the right direction"


def test_a_pan_never_doubles_back():
    """One deliberate move, not a search."""
    columns = [3] * 60 + [44] * 60
    xs = _x_positions(faceless_reframe.build_plan(_moving_scan(columns), TARGET_WIDTH, TARGET_HEIGHT))

    deltas = [b - a for a, b in zip(xs, xs[1:]) if b != a]
    assert deltas, "expected some movement"
    assert all(delta > 0 for delta in deltas), "the camera reversed direction mid-pan"


def test_a_single_brief_excursion_is_ignored():
    """A pan that lasts less than the dwell time is a distraction, not a move."""
    columns = [3] * 40 + [44] * 8 + [3] * 60  # away for 0.8s, then back
    plan = faceless_reframe.build_plan(_moving_scan(columns), TARGET_WIDTH, TARGET_HEIGHT)

    assert len(set(_x_positions(plan))) == 1


# --- framing continuity between scenes --------------------------------------


def _still_plan(x: int, y: int = 0):
    from app.pipeline.reframe.models import CropWindow, ReframePlan

    return ReframePlan(
        mode_used=ReframeMode.FACELESS_COOKING, windows=[CropWindow(time=0.0, x=x, y=y, width=608, height=1080)]
    )


def test_near_identical_framings_on_neighbouring_scenes_are_snapped_together():
    """One bowl then the next, same camera: a 40px shift at the cut reads as a
    judder rather than an edit."""
    plans = [_still_plan(300), _still_plan(340), _still_plan(320)]

    faceless_reframe.align_adjacent_plans(plans, SOURCE_WIDTH, SOURCE_HEIGHT)

    assert len({plan.windows[0].x for plan in plans}) == 1


def test_genuinely_different_framings_are_left_alone():
    """A cut to the other side of the kitchen is an edit, not a judder."""
    plans = [_still_plan(100), _still_plan(1200)]

    faceless_reframe.align_adjacent_plans(plans, SOURCE_WIDTH, SOURCE_HEIGHT)

    assert [plan.windows[0].x for plan in plans] == [100, 1200]


def test_a_panning_scene_breaks_the_run_and_keeps_its_own_movement():
    from app.pipeline.reframe.models import CropWindow, ReframePlan

    panning = ReframePlan(
        mode_used=ReframeMode.FACELESS_COOKING,
        windows=[
            CropWindow(time=0.0, x=300, y=0, width=608, height=1080),
            CropWindow(time=3.0, x=900, y=0, width=608, height=1080),
        ],
    )
    plans = [_still_plan(300), panning, _still_plan(880), _still_plan(900)]

    faceless_reframe.align_adjacent_plans(plans, SOURCE_WIDTH, SOURCE_HEIGHT)

    assert [w.x for w in panning.windows] == [300, 900]  # untouched
    assert plans[2].windows[0].x == plans[3].windows[0].x  # the pair after it settled


def test_alignment_tolerates_scenes_with_no_plan_yet():
    plans = [_still_plan(300), None, _still_plan(320)]

    faceless_reframe.align_adjacent_plans(plans, SOURCE_WIDTH, SOURCE_HEIGHT)

    assert plans[0].windows[0].x == 300 and plans[2].windows[0].x == 320

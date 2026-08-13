import pytest

from app.pipeline.reframe.center_crop import build_static_window
from app.pipeline.reframe.models import ReframeMode
from app.pipeline.reframe.modes import resolve


def test_auto_mode_falls_back_to_center_crop_when_nothing_else_available():
    plan = resolve(
        video_path="fake.mp4",
        requested_mode=ReframeMode.AUTO,
        source_width=1920,
        source_height=1080,
        target_width=720,
        target_height=1280,
    )
    assert plan.mode_used == ReframeMode.CENTER_CROP
    assert plan.fallback_reason is not None
    assert len(plan.windows) == 1


def test_center_crop_mode_never_consults_other_detectors():
    plan = resolve(
        video_path="fake.mp4",
        requested_mode=ReframeMode.CENTER_CROP,
        source_width=1920,
        source_height=1080,
        target_width=720,
        target_height=1280,
    )
    assert plan.mode_used == ReframeMode.CENTER_CROP
    assert plan.fallback_reason is None


def test_center_crop_geometry_landscape_to_portrait():
    window = build_static_window(source_width=1920, source_height=1080, target_width=720, target_height=1280)
    # 9:16 target is narrower than 16:9 source -> full height kept, width cropped and centered.
    assert window.height == 1080
    assert window.width == round(1080 * 720 / 1280)
    assert window.x == (1920 - window.width) // 2
    assert window.y == 0


@pytest.mark.parametrize(
    "requested_mode,expected_chain_head",
    [
        (ReframeMode.ACTIVE_SPEAKER, ReframeMode.ACTIVE_SPEAKER),
        (ReframeMode.FACE_TRACKING, ReframeMode.FACE_TRACKING),
    ],
)
def test_all_modes_eventually_reach_center_crop(requested_mode, expected_chain_head):
    plan = resolve(
        video_path="fake.mp4",
        requested_mode=requested_mode,
        source_width=1920,
        source_height=1080,
        target_width=720,
        target_height=1280,
    )
    assert plan.mode_used == ReframeMode.CENTER_CROP

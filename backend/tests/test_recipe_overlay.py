from __future__ import annotations

import cv2
import numpy as np

from app.pipeline.recipe.overlay_detect import OverlayBox, detect_static_overlays, overlap_fraction

WIDTH, HEIGHT = 512, 288
SOURCE_WIDTH, SOURCE_HEIGHT = 1920, 1080


def _write_frames(tmp_path, count: int, draw) -> list:
    """`count` frames of changing *footage-like* content -- smooth shapes that
    move -- with `draw(frame, i)` stamping whatever stays fixed.

    Per-pixel noise would be the wrong model: real video is smooth, so its
    edges are sparse, and that is what makes a logo's outline stand out.
    """
    rng = np.random.default_rng(7)
    paths = []
    for index in range(count):
        frame = np.full((HEIGHT, WIDTH), 90, dtype=np.uint8)
        for _ in range(6):  # moving scene content
            cx, cy = rng.integers(0, WIDTH), rng.integers(0, HEIGHT)
            cv2.circle(frame, (int(cx), int(cy)), int(rng.integers(20, 70)), int(rng.integers(30, 220)), -1)
        frame = cv2.GaussianBlur(frame, (9, 9), 0)
        draw(frame, index)
        path = tmp_path / f"probe_{index:06d}.jpg"
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        paths.append(path)
    return paths


def test_a_corner_watermark_is_found(tmp_path):
    """The real case: a channel logo burned into the top-right corner."""

    def stamp(frame, _index):
        cv2.rectangle(frame, (440, 14), (490, 48), 255, -1)
        cv2.putText(frame, "TV", (445, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)

    boxes = detect_static_overlays(_write_frames(tmp_path, 30, stamp), SOURCE_WIDTH, SOURCE_HEIGHT)

    assert boxes, "the watermark was not found"
    logo = boxes[0]
    assert logo.x > SOURCE_WIDTH * 0.7, "should be on the right"
    assert logo.y < SOURCE_HEIGHT * 0.3, "should be near the top"


def test_the_static_subject_of_a_locked_camera_is_not_mistaken_for_a_logo(tmp_path):
    """A fixed camera makes the worktop static too; only small edge graphics
    count, or the framing would be dragged around by the scene itself."""

    def stamp(frame, _index):
        cv2.rectangle(frame, (150, 90), (360, 210), 128, -1)  # big and central

    boxes = detect_static_overlays(_write_frames(tmp_path, 30, stamp), SOURCE_WIDTH, SOURCE_HEIGHT)

    assert all(box.x > SOURCE_WIDTH * 0.5 or box.width < SOURCE_WIDTH * 0.2 for box in boxes)
    assert not any(box.width > SOURCE_WIDTH * 0.3 and box.height > SOURCE_HEIGHT * 0.3 for box in boxes)


def test_specks_are_ignored(tmp_path):
    """A few static pixels of grain are not branding."""

    def stamp(frame, _index):
        cv2.rectangle(frame, (20, 270), (26, 276), 255, -1)

    assert detect_static_overlays(_write_frames(tmp_path, 30, stamp), SOURCE_WIDTH, SOURCE_HEIGHT) == []


def test_footage_with_no_overlay_at_all_reports_none(tmp_path):
    """The important negative: inventing a watermark would drag the framing
    away from the cooking for nothing."""

    def stamp(_frame, _index):
        return None

    assert detect_static_overlays(_write_frames(tmp_path, 30, stamp), SOURCE_WIDTH, SOURCE_HEIGHT) == []


def test_too_few_frames_is_no_answer_rather_than_a_wrong_one(tmp_path):
    def stamp(frame, _index):
        cv2.rectangle(frame, (440, 14), (490, 48), 255, -1)

    assert detect_static_overlays(_write_frames(tmp_path, 4, stamp), SOURCE_WIDTH, SOURCE_HEIGHT) == []


def test_overlap_is_measured_against_the_overlay_not_the_crop():
    logo = OverlayBox(x=1710, y=48, width=138, height=127)

    assert overlap_fraction([logo], 1232, 0, 608, 1080) > 0.9  # the crop that carried it
    assert overlap_fraction([logo], 1000, 0, 608, 1080) == 0.0  # shifted left, clean
    assert overlap_fraction([], 1232, 0, 608, 1080) == 0.0


def test_a_crop_clipping_the_edge_of_a_logo_scores_partially():
    logo = OverlayBox(x=1000, y=0, width=100, height=100)

    partial = overlap_fraction([logo], 950, 0, 100, 1080)  # covers half its width

    assert 0.4 < partial < 0.6

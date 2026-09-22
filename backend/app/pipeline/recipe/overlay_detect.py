"""Finding the channel watermark and other burned-in graphics.

A source taken from someone else's channel usually carries a logo in a corner,
and often a caption that never moves. Those survive the 9:16 crop about a
fifth of the time -- measured on a real run: seven of nine scenes were clean
by luck, two carried the logo -- which is not something to leave to luck when
the point of the feature is a clean short.

What identifies a watermark is not that its pixels never change. Measured on
real footage, the pixels under a semi-transparent logo vary almost as much as
anywhere else (0.84x the frame's median, against 0.86x for an ordinary patch
of worktop) because the picture behind it keeps changing. What does hold still
is its *outline*: the same edges appear in the same place frame after frame.
On that measure the same logo scored 0.40 against 0.03 for the rest of the
picture -- a separation wide enough to act on.

No model and no new dependency: the probe frames are already on disk from the
recipe analysis.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

MAX_FRAMES_SAMPLED = 60
MIN_FRAMES_REQUIRED = 8
EDGE_THRESHOLD = 12.0
# How often a pixel must be an edge to count as part of a graphic. Ordinary
# footage sits near 0.03; a logo's strokes sit far above this.
PERSISTENCE_MIN = 0.6
# ...and it must stand out from *this* footage, not merely clear a fixed bar.
# Grainy video has edges everywhere; without this the grain itself would read
# as branding.
PERSISTENCE_MARGIN = 0.2
# What a watermark is not: the locked-off subject in the middle of frame, nor
# a speck of static grain.
MAX_AREA_FRACTION = 0.04
MIN_AREA_FRACTION = 0.0015
MIN_SIDE_FRACTION = 0.02
# A logo is legible, so at least one of its raw strokes spans a real distance.
# Checked before the strokes are dilated together: dilation inflates a speck
# of grain into something that would otherwise clear the size floor.
MIN_EXTENT_FRACTION = 0.04
EDGE_MARGIN_FRACTION = 0.25
BOX_PADDING_FRACTION = 0.25


class OverlayBox(BaseModel):
    """A burned-in graphic, in source pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)


def detect_static_overlays(
    frame_paths: list[Path], source_width: int, source_height: int, max_boxes: int = 4
) -> list[OverlayBox]:
    """Graphics whose outline sits in the same place all the way through."""
    frames = _load(frame_paths)
    if len(frames) < MIN_FRAMES_REQUIRED:
        return []

    persistence = _edge_persistence(frames)
    threshold = max(PERSISTENCE_MIN, float(np.percentile(persistence, 97)) + PERSISTENCE_MARGIN)
    if threshold >= 1.0:
        return []  # edges everywhere in every frame: grain, not graphics

    raw = (persistence > threshold).astype(np.uint8) * 255
    height, width = raw.shape

    # Keep only strokes long enough to be part of a graphic, then dilate those
    # so the separate strokes of one logo merge into a single box.
    legible = np.zeros_like(raw)
    _n, labelled, raw_stats, _c = cv2.connectedComponentsWithStats(raw, 8)
    for index, (_x, _y, box_width, box_height, _area) in enumerate(raw_stats[1:], start=1):
        if max(box_width, box_height) >= MIN_EXTENT_FRACTION * width:
            legible[labelled == index] = 255

    mask = cv2.dilate(legible, np.ones((7, 7), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    _count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)

    boxes = [
        _to_source_box(x, y, box_width, box_height, width, height, source_width, source_height)
        for x, y, box_width, box_height, _area in stats[1:]
        if _looks_like_an_overlay(x, y, box_width, box_height, width, height)
    ]
    boxes.sort(key=lambda box: -box.area)
    return boxes[:max_boxes]


def _load(frame_paths: list[Path]) -> list[np.ndarray]:
    sampled = list(frame_paths)
    if len(sampled) > MAX_FRAMES_SAMPLED:
        sampled = sampled[:: max(1, len(sampled) // MAX_FRAMES_SAMPLED)][:MAX_FRAMES_SAMPLED]
    frames = []
    for path in sampled:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            frames.append(image)
    if frames and len({frame.shape for frame in frames}) != 1:
        return []
    return frames


def _edge_persistence(frames: list[np.ndarray]) -> np.ndarray:
    """Per pixel, the share of frames in which it is part of an edge."""
    maps = [
        (np.abs(cv2.Laplacian(cv2.GaussianBlur(frame, (3, 3), 0), cv2.CV_32F)) > EDGE_THRESHOLD).astype(np.float32)
        for frame in frames
    ]
    return np.stack(maps).mean(axis=0)


def _looks_like_an_overlay(x: int, y: int, box_width: int, box_height: int, width: int, height: int) -> bool:
    """Small, and pressed against an edge of the frame.

    A fixed camera leaves persistent edges in the scene itself -- the rim of a
    pan, the line of a worktop -- so position and size are what separate
    branding from the cooking.
    """
    frame_area = width * height
    box_area = box_width * box_height
    if not MIN_AREA_FRACTION * frame_area <= box_area <= MAX_AREA_FRACTION * frame_area:
        return False
    if box_width < MIN_SIDE_FRACTION * width or box_height < MIN_SIDE_FRACTION * height:
        return False
    margin_x = EDGE_MARGIN_FRACTION * width
    margin_y = EDGE_MARGIN_FRACTION * height
    near_side = x < margin_x or (x + box_width) > width - margin_x
    near_top_or_bottom = y < margin_y or (y + box_height) > height - margin_y
    return near_side or near_top_or_bottom


def _to_source_box(
    x: int, y: int, box_width: int, box_height: int, width: int, height: int, source_width: int, source_height: int
) -> OverlayBox:
    """Scales a box up to source pixels, with a margin: only the strokes of a
    logo are detected, and its soft outer glow needs excluding too."""
    pad_x = box_width * BOX_PADDING_FRACTION
    pad_y = box_height * BOX_PADDING_FRACTION
    left = max(0.0, x - pad_x)
    top = max(0.0, y - pad_y)
    right = min(float(width), x + box_width + pad_x)
    bottom = min(float(height), y + box_height + pad_y)
    scale_x = source_width / max(1, width)
    scale_y = source_height / max(1, height)
    return OverlayBox(
        x=int(left * scale_x),
        y=int(top * scale_y),
        width=int((right - left) * scale_x),
        height=int((bottom - top) * scale_y),
    )


def overlap_fraction(boxes: list[OverlayBox], x: int, y: int, crop_width: int, crop_height: int) -> float:
    """How much of the worst overlay would be on screen, 0..1.

    Same shape as the face measure, so the framing scorer can treat both the
    same way: what matters is whether the viewer sees it.
    """
    worst = 0.0
    for box in boxes:
        overlap_w = max(0, min(box.x + box.width, x + crop_width) - max(box.x, x))
        overlap_h = max(0, min(box.y + box.height, y + crop_height) - max(box.y, y))
        if overlap_w <= 0 or overlap_h <= 0:
            continue
        worst = max(worst, (overlap_w * overlap_h) / max(1, box.area))
    return worst

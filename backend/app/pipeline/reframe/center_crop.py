"""The one reframe mode that always works (PRD S12/S14 fallback floor).

Pure geometry, no ML — a single static crop window centered on the
source frame, scaled to the target aspect ratio. Everything else in
`reframe/` may fail; this must not.
"""

from __future__ import annotations

from app.pipeline.reframe.models import CropWindow


def target_crop_size(source_width: int, source_height: int, target_width: int, target_height: int) -> tuple[int, int]:
    """The crop rectangle size (not position) that fits target_ratio inside the source frame."""
    target_ratio = target_width / target_height
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        # Source is relatively wider than the target: crop width, keep full height.
        return round(source_height * target_ratio), source_height
    # Source is relatively taller/narrower than the target: crop height, keep full width.
    return source_width, round(source_width / target_ratio)


def build_static_window(source_width: int, source_height: int, target_width: int, target_height: int) -> CropWindow:
    crop_width, crop_height = target_crop_size(source_width, source_height, target_width, target_height)
    x = (source_width - crop_width) // 2
    y = (source_height - crop_height) // 2
    return CropWindow(time=0.0, x=x, y=y, width=crop_width, height=crop_height)

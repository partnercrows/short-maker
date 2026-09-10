"""Checking the faceless promise, and what to do when it can't be kept
(PRD S17, S45).

Choosing a framing is not the same as verifying it. This replays the chosen
crop path over the frames that were already scanned and measures how much of
a face actually lands inside the output. If a face got in, it climbs a ladder
of increasingly aggressive answers -- and if none of them work it says so
plainly and leaves the decision to the user.

Blurring is never one of the answers (PRD S45). The goal is to get the face
out of the frame, not to smear it.
"""

from __future__ import annotations

from app.pipeline.recipe.faceless_reframe import FacelessScan, _face_overlap, build_plan, scan
from app.pipeline.recipe.models import SceneFaceCheck
from app.pipeline.reframe.models import ReframeMode, ReframePlan
from app.pipeline.render import interpolated_window

# A sliver of an ear at the edge of one frame is not a face on screen; a face
# in one frame out of fifty is. These thresholds are what "faceless" means.
FACE_CLEAN_OVERLAP = 0.10
FACE_CLEAN_RATIO = 0.02

_ZOOM_LADDER = (1.0, 1.25, 1.5)


def validate_plan(scan_result: FacelessScan, plan: ReframePlan) -> tuple[float, float]:
    """(worst single-frame face overlap, fraction of frames with an intrusion)."""
    if not scan_result.samples or not plan.windows:
        return 0.0, 0.0
    worst = 0.0
    intrusions = 0
    for sample in scan_result.samples:
        window = interpolated_window(plan.windows, sample.time)
        overlap = _face_overlap(sample.faces, window.x, window.y, window.width, window.height)
        worst = max(worst, overlap)
        if overlap > FACE_CLEAN_OVERLAP:
            intrusions += 1
    return worst, intrusions / len(scan_result.samples)


def resolve_faceless(
    *,
    video_path: str,
    target_width: int,
    target_height: int,
    faceless: bool = True,
) -> tuple[ReframePlan, SceneFaceCheck]:
    """Frame one already-cut scene, climbing the ladder until faces are out.

    Every rung reuses a single scan of the scene, so the ladder costs almost
    nothing beyond the first decode.
    """
    scan_result = scan(video_path, detect_faces=faceless)

    if not faceless:
        plan = build_plan(scan_result, target_width, target_height, avoid_faces=False)
        return plan, SceneFaceCheck(status="clean", strategy_used="dynamic_crop")

    attempts: list[tuple[str, ReframePlan, float, float]] = []
    for zoom in _ZOOM_LADDER:
        plan = build_plan(scan_result, target_width, target_height, zoom=zoom)
        worst, ratio = validate_plan(scan_result, plan)
        strategy = "dynamic_crop" if zoom == 1.0 else f"zoom_{zoom:g}"
        if _is_clean(worst, ratio):
            status = "clean" if zoom == 1.0 else "reframed"
            return plan, SceneFaceCheck(
                status=status, face_frame_ratio=round(ratio, 4), worst_overlap=round(worst, 4), strategy_used=strategy
            )
        attempts.append((strategy, plan, worst, ratio))

    # A locked-off shot that avoids the face beats a moving one that doesn't.
    for zoom in _ZOOM_LADDER:
        plan = build_plan(scan_result, target_width, target_height, zoom=zoom, static=True)
        worst, ratio = validate_plan(scan_result, plan)
        if _is_clean(worst, ratio):
            return plan, SceneFaceCheck(
                status="reframed",
                face_frame_ratio=round(ratio, 4),
                worst_overlap=round(worst, 4),
                strategy_used=f"static_avoid_{zoom:g}",
            )
        attempts.append((f"static_avoid_{zoom:g}", plan, worst, ratio))

    # Nothing worked. Keep the least bad framing and say so, rather than
    # blurring or silently shipping the cook's face (PRD S45).
    strategy, plan, worst, ratio = min(attempts, key=lambda attempt: (attempt[3], attempt[2]))
    return plan, SceneFaceCheck(
        status="warning",
        face_frame_ratio=round(ratio, 4),
        worst_overlap=round(worst, 4),
        strategy_used=strategy,
        message="A face could not be fully kept out of this scene. Replace it, adjust the crop, or keep it as is.",
    )


def _is_clean(worst_overlap: float, face_frame_ratio: float) -> bool:
    return worst_overlap < FACE_CLEAN_OVERLAP and face_frame_ratio < FACE_CLEAN_RATIO


def center_fallback_plan(source_width: int, source_height: int, target_width: int, target_height: int) -> ReframePlan:
    """The floor, for a scene whose video could not be scanned at all: the
    same pure-geometry centre crop AI Clipper falls back to."""
    from app.pipeline.reframe.center_crop import build_static_window

    return ReframePlan(
        mode_used=ReframeMode.CENTER_CROP,
        fallback_reason="Scene could not be scanned; used a centre crop.",
        windows=[build_static_window(source_width, source_height, target_width, target_height)],
    )

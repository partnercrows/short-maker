"""Framing a cooking scene 9:16 without the cook's face in it (PRD S14-S16).

AI Clipper's reframing hunts for a face. Here the face is the thing to get
*out* of frame, and what we want instead is wherever the cooking is actually
happening -- the board, the pan, the hands.

There is no object detector in this app, and adding one (ultralytics + torch,
about two gigabytes) would wreck the packaged sidecar. What is available is
motion: in a cooking shot, the moving pixels are the hands, the knife, the
sauce going in. So the crop follows motion, is pushed away from any detected
face, and is pulled gently back to centre when nothing is moving -- which is
exactly the plating shot the PRD wants centred.

The honest limit, stated up front: on a 16:9 source a 9:16 crop keeps the
full height, so at zoom 1.0 this can only move sideways. When the face is
directly above the pan the only way out is to zoom in, which `face_check`
does, at the cost of some sharpness.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.pipeline.common.face_detector import FaceBox, YuNetFaceDetector
from app.pipeline.reframe.center_crop import target_crop_size
from app.pipeline.reframe.models import CropWindow, ReframeMode, ReframePlan
from app.pipeline.reframe.smoothing import segment_hold_and_pan, smooth_positions
from pydantic import BaseModel

FACELESS_STRIDE = 3
SALIENCY_WIDTH = 320
COLUMN_BINS = 48
ROW_BINS = 27
# Deliberately below AI Clipper's 0.7: here a missed face is a visible mistake
# in the output, while a false positive only nudges the crop.
FACE_SCORE_THRESHOLD = 0.5
FACE_DETECT_WIDTH = 640
FACE_DILATE = 0.35  # grow the box for hair, chin and neck
# Every term below is a fraction in 0..1, so these weights mean what they say:
# a window showing a whole face is worse than one containing all the motion.
FACE_PENALTY = 1.5
CENTER_BIAS = 0.2
POSITION_STEP = 16
MOTION_THRESHOLD = 12


class FacelessSample(BaseModel):
    time: float
    column_energy: list[float]
    row_energy: list[float]
    total_motion: float
    faces: list[FaceBox] = []


class FacelessScan(BaseModel):
    """One decode of a scene, reusable by every rung of the fallback ladder."""

    fps: float
    source_width: int
    source_height: int
    samples: list[FacelessSample] = []


def scan(video_path: str, *, frame_stride: int = FACELESS_STRIDE, detect_faces: bool = True) -> FacelessScan:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector: YuNetFaceDetector | None = None
    if detect_faces:
        try:
            detector = YuNetFaceDetector(score_threshold=FACE_SCORE_THRESHOLD)
        except FileNotFoundError:
            detector = None  # no model on disk: framing still works, face avoidance doesn't

    samples: list[FacelessSample] = []
    previous_gray: np.ndarray | None = None
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % frame_stride != 0:
                frame_index += 1
                continue

            small = _downscale(frame, SALIENCY_WIDTH)
            gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
            if previous_gray is not None and previous_gray.shape == gray.shape:
                mask = _motion_mask(previous_gray, gray)
                column_energy = _rebin(mask.sum(axis=0), COLUMN_BINS)
                row_energy = _rebin(mask.sum(axis=1), ROW_BINS)
                total_motion = float(mask.mean())
            else:
                column_energy = [0.0] * COLUMN_BINS
                row_energy = [0.0] * ROW_BINS
                total_motion = 0.0
            previous_gray = gray

            samples.append(
                FacelessSample(
                    time=frame_index / fps,
                    column_energy=column_energy,
                    row_energy=row_energy,
                    total_motion=total_motion,
                    faces=_detect_faces(detector, frame, source_width),
                )
            )
            frame_index += 1
    finally:
        capture.release()

    return FacelessScan(fps=fps, source_width=source_width, source_height=source_height, samples=samples)


def _downscale(frame: np.ndarray, width: int) -> np.ndarray:
    height = max(1, int(frame.shape[0] * width / max(1, frame.shape[1])))
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def _motion_mask(previous_gray: np.ndarray, gray: np.ndarray) -> np.ndarray:
    difference = cv2.absdiff(gray, previous_gray)
    _, mask = cv2.threshold(difference, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel) / 255.0


def _rebin(values: np.ndarray, bins: int) -> list[float]:
    if values.size == 0:
        return [0.0] * bins
    edges = np.linspace(0, values.size, bins + 1).astype(int)
    return [float(values[low:high].sum()) if high > low else 0.0 for low, high in zip(edges, edges[1:])]


def _detect_faces(detector: YuNetFaceDetector | None, frame: np.ndarray, source_width: int) -> list[FaceBox]:
    if detector is None:
        return []
    detect_frame = _downscale(frame, FACE_DETECT_WIDTH) if frame.shape[1] > FACE_DETECT_WIDTH else frame
    scale = source_width / max(1, detect_frame.shape[1])
    try:
        boxes = detector.detect(detect_frame)
    except Exception:  # noqa: BLE001 -- a detection hiccup must not lose the whole scan
        return []
    return [
        FaceBox(
            x=int(box.x * scale),
            y=int(box.y * scale),
            width=int(box.width * scale),
            height=int(box.height * scale),
            score=box.score,
        )
        for box in boxes
    ]


def build_plan(
    scan_result: FacelessScan,
    target_width: int,
    target_height: int,
    *,
    zoom: float = 1.0,
    avoid_faces: bool = True,
    static: bool = False,
) -> ReframePlan:
    """Pick a crop path over the scene: towards the action, away from faces."""
    source_width = scan_result.source_width
    source_height = scan_result.source_height
    crop_height = max(16, min(source_height, int(round(source_height / max(1.0, zoom)))))
    crop_width, crop_height = _crop_size(source_width, source_height, crop_height, target_width, target_height)

    positions = [
        _best_position(sample, scan_result, crop_width, crop_height, avoid_faces=avoid_faces)
        for sample in scan_result.samples
    ]
    if not positions:
        centered = ((source_width - crop_width) // 2, (source_height - crop_height) // 2)
        positions = [centered]

    if static:
        x, y = _static_position(positions, scan_result, crop_width, crop_height, avoid_faces=avoid_faces)
        windows = [CropWindow(time=0.0, x=x, y=y, width=crop_width, height=crop_height)]
        return ReframePlan(mode_used=ReframeMode.FACELESS_COOKING, windows=windows)

    times = [sample.time for sample in scan_result.samples] or [0.0]
    smooth_x = smooth_positions([float(x) for x, _ in positions], ema_alpha=0.12, deadband_px=0.06 * source_width)
    smooth_y = smooth_positions([float(y) for _, y in positions], ema_alpha=0.12, deadband_px=0.06 * source_height)

    windows = [
        CropWindow(
            time=time,
            x=_clamp(int(round(x)), 0, source_width - crop_width),
            y=_clamp(int(round(y)), 0, source_height - crop_height),
            width=crop_width,
            height=crop_height,
        )
        for time, x, y in zip(times, _hold_and_pan(times, smooth_x), _hold_and_pan(times, smooth_y))
    ]

    # render._interpolated_window takes width/height from the earlier keyframe
    # and only interpolates x/y, so a plan must never change crop size midway.
    assert len({(window.width, window.height) for window in windows}) == 1
    return ReframePlan(mode_used=ReframeMode.FACELESS_COOKING, windows=windows)


def _crop_size(
    source_width: int, source_height: int, crop_height: int, target_width: int, target_height: int
) -> tuple[int, int]:
    base_width, base_height = target_crop_size(source_width, source_height, target_width, target_height)
    if crop_height >= base_height:
        return base_width, base_height
    scale = crop_height / base_height
    width = max(16, min(source_width, int(round(base_width * scale))))
    return width, crop_height


def _best_position(
    sample: FacelessSample,
    scan_result: FacelessScan,
    crop_width: int,
    crop_height: int,
    *,
    avoid_faces: bool,
) -> tuple[int, int]:
    source_width = scan_result.source_width
    source_height = scan_result.source_height
    xs = list(range(0, max(1, source_width - crop_width + 1), POSITION_STEP))
    ys = list(range(0, max(1, source_height - crop_height + 1), POSITION_STEP))
    if not xs:
        xs = [0]
    if not ys:
        ys = [0]

    faces = sample.faces if avoid_faces else []
    column_total = sum(sample.column_energy) or 1.0
    row_total = sum(sample.row_energy) or 1.0

    best_score = float("-inf")
    best = (xs[0], ys[0])
    for x in xs:
        # Share of the frame's horizontal motion this window would contain.
        reward_x = _energy_in(sample.column_energy, x, crop_width, source_width) / column_total
        for y in ys:
            reward_y = _energy_in(sample.row_energy, y, crop_height, source_height) / row_total
            reward = (reward_x + reward_y) / 2
            # How much of the most exposed face would be on screen, 0..1.
            penalty = FACE_PENALTY * _face_overlap(faces, x, y, crop_width, crop_height)
            # Distance from centre, 0..1. Not scaled by motion: in a shot
            # where nothing moves -- a plating hero shot -- this is the only
            # term left, and centring it is the right answer (PRD S16).
            center = CENTER_BIAS * (
                abs((x + crop_width / 2) - source_width / 2) / max(1.0, source_width / 2)
                + abs((y + crop_height / 2) - source_height / 2) / max(1.0, source_height / 2)
            ) / 2
            score = reward - penalty - center
            if score > best_score:
                best_score = score
                best = (x, y)
    return best


def _static_position(
    positions: list[tuple[int, int]],
    scan_result: FacelessScan,
    crop_width: int,
    crop_height: int,
    *,
    avoid_faces: bool,
) -> tuple[int, int]:
    """One fixed window for the whole scene: the position that keeps faces out
    for the longest. A still frame with no face beats a moving one with."""
    candidates = sorted({position for position in positions})
    if not candidates:
        return ((scan_result.source_width - crop_width) // 2, (scan_result.source_height - crop_height) // 2)
    best = candidates[0]
    best_cost = float("inf")
    for x, y in candidates:
        overlap = sum(
            _face_overlap(sample.faces if avoid_faces else [], x, y, crop_width, crop_height)
            for sample in scan_result.samples
        )
        reward = sum(
            _energy_in(sample.column_energy, x, crop_width, scan_result.source_width) for sample in scan_result.samples
        )
        cost = overlap * 1000 - reward
        if cost < best_cost:
            best_cost = cost
            best = (x, y)
    return best


def _energy_in(energy: list[float], start: int, length: int, source_length: int) -> float:
    if not energy or source_length <= 0:
        return 0.0
    bin_size = source_length / len(energy)
    low = int(start / bin_size)
    high = int(min(len(energy), (start + length) / bin_size + 1))
    return float(sum(energy[low:high]))


def _face_overlap(faces: list[FaceBox], x: int, y: int, crop_width: int, crop_height: int) -> float:
    """How much face the viewer would see, 0..1.

    Measured against the smaller of the face and the window on purpose: a
    small face fully inside the crop scores 1.0 because it is entirely
    visible, and a face larger than the crop also scores 1.0 because the
    output is then nothing but face. Dividing by the face area alone would
    let a close-up read as "mostly outside the frame".
    """
    worst = 0.0
    crop_area = max(1.0, float(crop_width) * float(crop_height))
    for face in faces:
        pad_x = face.width * FACE_DILATE / 2
        pad_y = face.height * FACE_DILATE / 2
        fx1, fy1 = face.x - pad_x, face.y - pad_y
        fx2, fy2 = face.x + face.width + pad_x, face.y + face.height + pad_y
        overlap_w = max(0.0, min(fx2, x + crop_width) - max(fx1, x))
        overlap_h = max(0.0, min(fy2, y + crop_height) - max(fy1, y))
        face_area = max(1.0, (fx2 - fx1) * (fy2 - fy1))
        worst = max(worst, (overlap_w * overlap_h) / min(face_area, crop_area))
    return worst


def _hold_and_pan(times: list[float], values: list[float]) -> list[float]:
    """Turn a continuous position series into holds joined by eased pans, so
    the camera reads as deliberate rather than nervous (PRD S16)."""
    if len(values) < 2:
        return values
    spread = max(values) - min(values)
    if spread < 1.0:
        return values

    tolerance = 0.08 * spread
    runs: list[tuple[float, float, float]] = []
    run_start = times[0]
    run_values = [values[0]]
    for time, value in zip(times[1:], values[1:]):
        median = float(np.median(run_values))
        if abs(value - median) <= tolerance:
            run_values.append(value)
            continue
        runs.append((run_start, time, median))
        run_start = time
        run_values = [value]
    runs.append((run_start, times[-1], float(np.median(run_values))))

    keyframes = segment_hold_and_pan(runs, pan_duration=0.6, pan_steps=8)
    if not keyframes:
        return values
    keyframe_times = [time for time, _ in keyframes]
    keyframe_values = [value for _, value in keyframes]
    return list(np.interp(times, keyframe_times, keyframe_values))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value)) if high >= low else low

"""Camera-position smoothing (PRD S13): the crop must not instantly jump
between speakers, or jitter on every tiny per-frame detection wobble.

Reimplements the smoothing *idea* validated in the auto-clipper audit
(EMA + deadband) independently -- not its code.
"""

from __future__ import annotations


def smooth_positions(values: list[float], ema_alpha: float = 0.25, deadband_px: float = 12.0) -> list[float]:
    """EMA-smooths a continuous position series (used by face_tracking,
    which has no discrete "who's active" decision to hold steady on).

    The deadband gates whether a new sample updates the *target* the EMA
    chases, not the EMA's own output. Comparing against the previous
    output (an earlier version of this function did that) makes small
    per-frame deltas that individually fall under the deadband pile up
    silently until they cross it, then jump by the whole accumulated
    amount at once -- a stutter, then a jump. Gating the target instead
    means real movements are smoothly approached from the first sample
    that triggers them, with no discarded motion to dump later.
    """
    if not values:
        return []

    target = values[0]
    smoothed = [target]
    for value in values[1:]:
        if abs(value - target) >= deadband_px:
            target = value
        smoothed.append(ema_alpha * target + (1 - ema_alpha) * smoothed[-1])
    return smoothed


def _ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def segment_hold_and_pan(
    segments: list[tuple[float, float, float]], pan_duration: float = 0.3, pan_steps: int = 6
) -> list[tuple[float, float]]:
    """Builds camera keyframes from discrete (start, end, target_x) segments
    (PRD S13's own diagram: hold on speaker A, one smooth pan, hold on
    speaker B -- not continuous per-frame tracking, which reads as a
    hesitant, jittery cameraman rather than a deliberate pan).

    Holds steady at each segment's target for its full duration, except a
    short eased pan at the start of every segment after the first, moving
    from the previous target to the new one. Time gaps between segments
    (no confident active speaker) hold at the previous target rather than
    drifting toward the next one early -- so the pan only starts once the
    next segment actually begins.
    """
    keyframes: list[tuple[float, float]] = []
    previous_target: float | None = None

    for start, end, target_x in segments:
        if previous_target is None:
            keyframes.append((start, target_x))
        else:
            pan_end = min(start + pan_duration, end)
            span = pan_end - start
            for step in range(pan_steps + 1):
                t = step / pan_steps
                x = previous_target + (target_x - previous_target) * _ease_in_out(t)
                keyframes.append((start + span * t, x))
        keyframes.append((end, target_x))
        previous_target = target_x

    return keyframes

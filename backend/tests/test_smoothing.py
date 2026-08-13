from app.pipeline.reframe.smoothing import segment_hold_and_pan, smooth_positions


def test_empty_input_returns_empty():
    assert smooth_positions([]) == []


def test_constant_input_stays_constant():
    result = smooth_positions([100.0] * 5)
    assert all(abs(v - 100.0) < 1e-6 for v in result)


def test_deadband_suppresses_tiny_movement():
    # Jumps smaller than the deadband never update the target, so the
    # output should settle exactly on the first value and stay there.
    result = smooth_positions([100.0, 103.0, 100.0, 104.0], deadband_px=12.0)
    assert all(abs(v - 100.0) < 1e-6 for v in result)


def test_large_jump_moves_smoothly_without_stutter():
    result = smooth_positions([100.0] + [400.0] * 20, ema_alpha=0.3, deadband_px=12.0)
    # Monotonic approach toward the new target -- no discarded-then-dumped jump.
    diffs = [b - a for a, b in zip(result, result[1:])]
    assert all(d >= -1e-6 for d in diffs)  # never moves backward
    assert result[-1] > result[0] + 100


def test_single_segment_holds_steady_at_its_target():
    keyframes = segment_hold_and_pan([(0.0, 5.0, 100.0)])
    assert keyframes == [(0.0, 100.0), (5.0, 100.0)]


def test_two_segments_pan_between_targets_at_the_switch():
    keyframes = segment_hold_and_pan([(0.0, 5.0, 100.0), (5.0, 10.0, 300.0)], pan_duration=0.3, pan_steps=2)

    times = [t for t, _ in keyframes]
    assert times == sorted(times)  # strictly non-decreasing in time
    assert keyframes[0] == (0.0, 100.0)
    assert keyframes[-1] == (10.0, 300.0)

    # Holds at 100 right up to the switch, and the pan finishes at 300
    # within pan_duration of the switch -- not gradually beforehand.
    pre_switch = [x for t, x in keyframes if t <= 5.0]
    assert all(abs(x - 100.0) < 1e-6 for x in pre_switch)
    post_pan = [x for t, x in keyframes if t >= 5.3]
    assert all(abs(x - 300.0) < 1e-6 for x in post_pan)


def test_gap_between_segments_holds_previous_target():
    # A silent gap from t=5 to t=8 should NOT drift toward the next
    # speaker early -- the pan only starts once the next segment begins.
    keyframes = segment_hold_and_pan([(0.0, 5.0, 100.0), (8.0, 10.0, 300.0)], pan_duration=0.3, pan_steps=2)
    just_before_next_segment = [x for t, x in keyframes if t <= 8.0]
    assert all(abs(x - 100.0) < 1e-6 for x in just_before_next_segment)

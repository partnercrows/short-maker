"""Rendering one scene into a segment that can be joined with the others.

Two things make this different from `app/pipeline/render.py`, which renders a
whole AI Clipper clip:

1. It encodes once. `render()` writes an mp4v intermediate with OpenCV and
   then re-encodes it with ffmpeg -- acceptable for one clip, wasteful when a
   recipe video is fifteen of them. Here the cropped frames go straight into
   ffmpeg's stdin.
2. Every segment comes out *identical* in shape -- same fps, size, pixel
   format, timebase, and always with an audio track, silent if the source had
   none. That uniformity is what lets the finished video be assembled by
   stream copy, so changing the audio or the order later costs no re-encode
   at all (PRD S28).
"""

from __future__ import annotations

from pathlib import Path

import cv2

from app.core.ffmpeg_utils import cut_subclip, ffmpeg_path, has_audio_stream, run_with_frame_pipe
from app.pipeline.recipe.models import AudioMode, FramingMode
from app.pipeline.recipe.overlay_detect import OverlayBox, overlap_fraction
from app.pipeline.reframe.models import ReframePlan
from app.pipeline.render import interpolated_window

SCENE_FPS = 30
SCENE_WIDTH = 720
SCENE_HEIGHT = 1280
# How much wider than the 9:16 crop the balanced mode tries to show.
BALANCED_EXPANSION = 1.7
PAD_BLUR_SIGMA = 25
SEGMENT_NAME = "source_segment.mp4"
SCENE_NAME = "scene.mp4"


def render_scene(
    source_video: str,
    *,
    start: float,
    duration: float,
    plan: ReframePlan,
    scene_dir: Path,
    target_width: int = SCENE_WIDTH,
    target_height: int = SCENE_HEIGHT,
    fps: int = SCENE_FPS,
    framing: FramingMode = FramingMode.CROP,
    overlays: list[OverlayBox] | None = None,
) -> Path:
    scene_dir.mkdir(parents=True, exist_ok=True)
    segment_path = scene_dir / SEGMENT_NAME
    scene_path = scene_dir / SCENE_NAME

    # Cut first: the crop plan's timestamps are relative to the scene, and
    # seeking a two-hour container with OpenCV is not dependable.
    cut_subclip(source_video, start, duration, str(segment_path))
    try:
        _crop_and_encode(
            segment_path, scene_path, plan, target_width, target_height, fps, duration, framing, overlays or []
        )
    finally:
        segment_path.unlink(missing_ok=True)
    return scene_path


def _crop_and_encode(
    segment_path: Path,
    scene_path: Path,
    plan: ReframePlan,
    target_width: int,
    target_height: int,
    fps: int,
    duration: float,
    framing: FramingMode = FramingMode.CROP,
    overlays: list[OverlayBox] | None = None,
) -> None:
    has_audio = has_audio_stream(str(segment_path))
    cmd = [
        ffmpeg_path(),
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{target_width}x{target_height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-i",
        str(segment_path),
    ]
    if has_audio:
        audio_map = ["-map", "1:a:0"]
    else:
        # A segment with no audio still needs a track, or the concat demuxer
        # refuses to join it to the segments that have one.
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
        audio_map = ["-map", "2:a:0"]

    cmd += [
        "-map",
        "0:v:0",
        *audio_map,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-g",
        str(fps * 2),
        "-r",
        str(fps),
        "-fps_mode",
        "cfr",
        "-video_track_timescale",
        "30000",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-af",
        "aresample=async=1:first_pts=0,apad",
        "-t",
        f"{duration:.3f}",
        str(scene_path),
    ]
    run_with_frame_pipe(
        cmd, _cropped_frames(segment_path, plan, target_width, target_height, fps, framing, overlays or [])
    )


def _cropped_frames(
    segment_path: Path,
    plan: ReframePlan,
    target_width: int,
    target_height: int,
    fps: int,
    framing: FramingMode = FramingMode.CROP,
    overlays: list[OverlayBox] | None = None,
):
    """Yields the scene's frames, cropped to the plan and resampled to a fixed
    frame rate so the pipe and the container agree on timing."""
    capture = cv2.VideoCapture(str(segment_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open segment: {segment_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS) or float(fps)
    windows = plan.windows
    try:
        output_index = 0
        source_index = 0
        ok, frame = capture.read()
        if not ok:
            return
        while True:
            output_time = output_index / fps
            # Advance the source until it catches up with the output clock:
            # this is what turns a variable or odd frame rate into clean CFR.
            while source_index / source_fps < output_time:
                ok, next_frame = capture.read()
                if not ok:
                    return
                frame = next_frame
                source_index += 1

            window = interpolated_window(windows, output_time)
            composed = compose_frame(frame, window, target_width, target_height, framing, overlays or [])
            yield composed.tobytes()
            output_index += 1
    finally:
        capture.release()


def audio_filter_for(mode: AudioMode, volume_percent: int) -> tuple[str | None, bool]:
    """(filter, mute) for the assemble step -- see PRD S27."""
    if mode is AudioMode.MUTE:
        return None, True
    if mode is AudioMode.LOWER:
        volume = max(0, min(100, volume_percent)) / 100.0
        return f"volume={volume:.2f}", False
    return None, False


def compose_frame(frame, window, target_width: int, target_height: int, framing: FramingMode, overlays):
    """Puts one source frame into the 9:16 output the chosen way.

    CROP fills the screen with the crop window, as before. BALANCED widens
    that window -- without letting a watermark back in -- and pads what is
    left. FIT keeps the entire frame. Padding is a blurred, screen-filling
    copy of the same picture rather than black bars, which keeps the video
    looking deliberate.
    """
    if framing is FramingMode.FIT:
        region = frame
    elif framing is FramingMode.BALANCED:
        region = _take(frame, _widen(window, frame.shape[1], frame.shape[0], overlays))
    else:
        region = _take(frame, window)

    if region.size == 0:
        region = frame

    if framing is FramingMode.CROP:
        return cv2.resize(region, (target_width, target_height), interpolation=cv2.INTER_LINEAR)

    scale = target_width / region.shape[1]
    foreground_height = max(1, min(target_height, int(round(region.shape[0] * scale))))
    foreground = cv2.resize(region, (target_width, foreground_height), interpolation=cv2.INTER_LINEAR)
    if foreground_height == target_height:
        return foreground

    canvas = _blurred_backdrop(region, target_width, target_height)
    top = (target_height - foreground_height) // 2
    canvas[top : top + foreground_height, 0:target_width] = foreground
    return canvas


def _take(frame, window):
    return frame[window.y : window.y + window.height, window.x : window.x + window.width]


def _widen(window, source_width: int, source_height: int, overlays):
    """A wider version of the crop window that still excludes any watermark.

    Widening is what buys back the composition the 9:16 crop threw away; it
    stops short of whatever the framing was avoiding in the first place.
    """
    from app.pipeline.reframe.models import CropWindow

    centre = window.x + window.width / 2
    already_clean = overlap_fraction(overlays, window.x, window.y, window.width, window.height) <= 0.01

    for factor in (BALANCED_EXPANSION, 1.5, 1.3, 1.15, 1.0):
        width = min(source_width, int(round(window.width * factor)))
        x = int(round(max(0, min(centre - width / 2, source_width - width))))
        if not already_clean or overlap_fraction(overlays, x, window.y, width, window.height) <= 0.01:
            return CropWindow(time=window.time, x=x, y=window.y, width=width, height=window.height)
    return window


def _blurred_backdrop(region, target_width: int, target_height: int):
    """The same picture, scaled to cover and blurred, so the bars are not dead
    space."""
    scale = max(target_width / region.shape[1], target_height / region.shape[0])
    cover = cv2.resize(
        region,
        (max(target_width, int(region.shape[1] * scale)), max(target_height, int(region.shape[0] * scale))),
        interpolation=cv2.INTER_LINEAR,
    )
    top = max(0, (cover.shape[0] - target_height) // 2)
    left = max(0, (cover.shape[1] - target_width) // 2)
    cover = cover[top : top + target_height, left : left + target_width]
    return cv2.GaussianBlur(cover, (0, 0), PAD_BLUR_SIGMA)

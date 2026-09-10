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
from app.pipeline.recipe.models import AudioMode
from app.pipeline.reframe.models import ReframePlan
from app.pipeline.render import interpolated_window

SCENE_FPS = 30
SCENE_WIDTH = 720
SCENE_HEIGHT = 1280
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
) -> Path:
    scene_dir.mkdir(parents=True, exist_ok=True)
    segment_path = scene_dir / SEGMENT_NAME
    scene_path = scene_dir / SCENE_NAME

    # Cut first: the crop plan's timestamps are relative to the scene, and
    # seeking a two-hour container with OpenCV is not dependable.
    cut_subclip(source_video, start, duration, str(segment_path))
    try:
        _crop_and_encode(segment_path, scene_path, plan, target_width, target_height, fps, duration)
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
    run_with_frame_pipe(cmd, _cropped_frames(segment_path, plan, target_width, target_height, fps))


def _cropped_frames(segment_path: Path, plan: ReframePlan, target_width: int, target_height: int, fps: int):
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
            cropped = frame[window.y : window.y + window.height, window.x : window.x + window.width]
            if cropped.size == 0:
                cropped = frame
            resized = cv2.resize(cropped, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
            yield resized.tobytes()
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

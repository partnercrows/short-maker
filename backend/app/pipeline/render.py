"""Renders a ReframePlan into an actual output video (PRD S15).

For this spike: OpenCV reads/crops/resizes frame-by-frame (frame-accurate
and simple to get right for a POC), then an FFmpeg subprocess muxes the
original audio track back in and encodes final H.264/AAC. Continuous
FFmpeg-filter-based cropping (avoiding the OpenCV re-encode pass
entirely) and hardware-accelerated encoding throughout are production
hardening for the MVP pass, not spike-blocking -- see
docs/ACTIVE_SPEAKER_SPIKE.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2

from app.core.ffmpeg_utils import ffmpeg_path
from app.pipeline.reframe.models import CropWindow, ReframePlan


def _interpolated_window(windows: list[CropWindow], timestamp: float) -> CropWindow:
    if len(windows) == 1 or timestamp <= windows[0].time:
        return windows[0]
    if timestamp >= windows[-1].time:
        return windows[-1]

    # windows is time-sorted; linear scan is fine at this scale (POC).
    for i in range(len(windows) - 1):
        a, b = windows[i], windows[i + 1]
        if a.time <= timestamp <= b.time:
            span = b.time - a.time
            t = (timestamp - a.time) / span if span > 0 else 0.0
            x = round(a.x + (b.x - a.x) * t)
            y = round(a.y + (b.y - a.y) * t)
            return CropWindow(time=timestamp, x=x, y=y, width=a.width, height=a.height)
    return windows[-1]


def render(video_path: str, plan: ReframePlan, output_path: str, target_width: int, target_height: int) -> None:
    windows = sorted(plan.windows, key=lambda w: w.time)
    if not windows:
        raise ValueError("ReframePlan has no windows to render")

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0

    silent_path = str(Path(output_path).with_suffix(".silent.mp4"))
    writer = cv2.VideoWriter(silent_path, cv2.VideoWriter.fourcc(*"mp4v"), fps, (target_width, target_height))

    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = frame_index / fps
            window = _interpolated_window(windows, timestamp)
            cropped = frame[window.y : window.y + window.height, window.x : window.x + window.width]
            resized = cv2.resize(cropped, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
            writer.write(resized)
            frame_index += 1
    finally:
        capture.release()
        writer.release()

    ffmpeg = ffmpeg_path()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            silent_path,
            "-i",
            video_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            output_path,
        ],
        check=True,
        capture_output=True,
    )
    Path(silent_path).unlink(missing_ok=True)

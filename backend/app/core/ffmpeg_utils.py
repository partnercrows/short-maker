"""Small shared FFmpeg/FFprobe wrappers. Every pipeline stage that needs to
shell out to either binary goes through here instead of hand-rolling its
own `shutil.which` + `subprocess.run` pair.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def ffmpeg_path() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found on PATH")
    return found


def ffprobe_path() -> str:
    found = shutil.which("ffprobe")
    if not found:
        raise RuntimeError("ffprobe not found on PATH")
    return found


class VideoMetadata:
    def __init__(self, duration: float, width: int, height: int, fps: float) -> None:
        self.duration = duration
        self.width = width
        self.height = height
        self.fps = fps


def probe_metadata(video_path: str) -> VideoMetadata:
    result = subprocess.run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            video_path,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) != 0 else 0.0
    return VideoMetadata(
        duration=float(data["format"]["duration"]),
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=fps,
    )


def extract_audio(video_path: str, output_wav_path: str, sample_rate: int = 16000) -> None:
    Path(output_wav_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            output_wav_path,
        ],
        check=True,
        capture_output=True,
    )


def cut_subclip(video_path: str, start: float, duration: float, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-ss",
            str(start),
            "-i",
            video_path,
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            output_path,
        ],
        check=True,
        capture_output=True,
    )

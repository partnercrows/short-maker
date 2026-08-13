"""Small shared FFmpeg/FFprobe wrappers. Every pipeline stage that needs to
shell out to either binary goes through here instead of hand-rolling its
own `shutil.which` + `subprocess.run` pair.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

# On this class of Windows setup, whether ffmpeg/ffprobe are actually on PATH
# depends entirely on which shell/session launched the sidecar -- a WinGet
# install (the common case) adds a Links shim dir to the *user* PATH, which a
# process started from a different session (a service, a differently-launched
# terminal, ...) won't have. Same category of fragility as the CUDA DLL PATH
# issue (see gpu_utils.py): fall back to searching common install locations
# instead of hard-failing the moment `shutil.which` comes back empty.
_FALLBACK_SEARCH_ROOTS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
    Path("C:/ffmpeg/bin"),
    Path("C:/Program Files/ffmpeg/bin"),
]


@lru_cache
def _find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found

    exe_name = f"{name}.exe"
    for root in _FALLBACK_SEARCH_ROOTS:
        if not root.is_dir():
            continue
        try:
            match = next(root.rglob(exe_name), None)
        except OSError:
            continue
        if match:
            return str(match)

    raise RuntimeError(f"{name} not found on PATH or in common install locations")


def ffmpeg_path() -> str:
    return _find_binary("ffmpeg")


def ffprobe_path() -> str:
    return _find_binary("ffprobe")


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

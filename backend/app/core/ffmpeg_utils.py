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


class FfmpegError(RuntimeError):
    """ffmpeg/ffprobe exited non-zero.

    `CalledProcessError`'s message is just the command line, so the actual
    complaint -- the one line of ffmpeg stderr that says what went wrong --
    never reached the job row. This carries that tail instead."""


def _run(cmd: list[str], *, text: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=text)
    except subprocess.CalledProcessError as exc:
        raise FfmpegError(f"{Path(cmd[0]).stem} failed (exit {exc.returncode}): {_stderr_tail(exc.stderr)}") from exc


def _stderr_tail(stderr: bytes | str | None, max_lines: int = 4) -> str:
    """The last few meaningful stderr lines. ffmpeg's stderr is mostly banner
    and progress noise; the reason it stopped is at the end."""
    if not stderr:
        return "no error output"
    text = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
    # splitlines() splits on CR as well as LF, so ffmpeg's carriage-returned
    # progress bar arrives as separate lines to filter out below.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    meaningful = [line for line in lines if not line.startswith(("frame=", "size=", "video:", "  "))]
    return " | ".join((meaningful or lines)[-max_lines:])


def probe_duration(path: str) -> float:
    """Duration in seconds -- works for an audio-only file too, unlike
    `probe_metadata()` which requires a video stream."""
    result = _run(
        [ffprobe_path(), "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


class NoVideoStreamError(RuntimeError):
    """Raised when a file we expected to be a video has no picture track at
    all -- either it never had one, or (the case actually seen in the wild)
    it's a partially-downloaded file whose video track stops long before its
    audio does, so a cut taken past that point contains audio only."""


class VideoMetadata:
    def __init__(self, duration: float, width: int, height: int, fps: float, video_duration: float | None = None) -> None:
        self.duration = duration
        self.width = width
        self.height = height
        self.fps = fps
        # How far the *picture* track actually runs. Normally the same as
        # `duration` (the container's, i.e. the longest stream's), but an
        # interrupted download can leave a file whose audio runs the full
        # length while the video stops early -- and everything downstream of
        # a cut (crop resolution, render) needs frames, not just audio.
        self.video_duration = duration if video_duration is None else video_duration


def probe_metadata(video_path: str) -> VideoMetadata:
    result = _run(
        [
            ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            video_path,
        ],
        text=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise NoVideoStreamError(f"No video stream found in {video_path}")
    stream = streams[0]
    num, den = stream["r_frame_rate"].split("/")
    fps = float(num) / float(den) if float(den) != 0 else 0.0
    duration = float(data["format"]["duration"])
    return VideoMetadata(
        duration=duration,
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=fps,
        video_duration=_stream_duration(stream, duration),
    )


def _stream_duration(stream: dict, container_duration: float) -> float:
    """The video stream's own duration, falling back to the container's when
    the format doesn't carry per-stream durations (common for Matroska/WebM),
    and never trusting a value longer than the container itself."""
    try:
        value = float(stream["duration"])
    except (KeyError, TypeError, ValueError):
        return container_duration
    if value <= 0:
        return container_duration
    return min(value, container_duration)


def extract_audio(video_path: str, output_wav_path: str, sample_rate: int = 16000) -> None:
    Path(output_wav_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
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
    )


def slice_audio(audio_path: str, start: float, duration: float, output_path: str) -> None:
    """Lossless sub-range cut of an audio file (no re-encode) -- used to
    split long audio into smaller pieces before handing it to Whisper."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_path(),
            "-y",
            "-i",
            audio_path,
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-c",
            "copy",
            output_path,
        ],
    )


def extract_frame(video_path: str, timestamp: float, output_path: str) -> None:
    """Grabs a single still frame at `timestamp` seconds -- used to seed an
    Intro Frame image from a clip's own rendered video."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_path(),
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-vframes",
            "1",
            output_path,
        ],
    )


def convert_image_to_png(input_path: str, output_path: str) -> None:
    """Re-encodes any ffmpeg-readable image (JPEG/WebP/PNG) to PNG at a fixed
    path -- used to normalize an uploaded Intro Frame image regardless of the
    format it was uploaded in."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
        [ffmpeg_path(), "-y", "-i", input_path, "-frames:v", "1", output_path],
    )


def cut_subclip(video_path: str, start: float, duration: float, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run(
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
    )

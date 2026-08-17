"""Standalone "Download YouTube Video/Audio" feature: paste a URL, check
which resolutions actually exist for that video, then download either
video+audio merged into one file, or audio only as an MP3. Uses yt-dlp
(free, open-source, no API key) as the engine; merging/transcoding reuses
the same ffmpeg binary the rest of the app already locates via
`ffmpeg_utils.ffmpeg_path()`.

Deliberately no DB persistence / download history here -- this is a one-shot
utility independent of the project/clip pipeline, not tied to a project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import yt_dlp
from pydantic import BaseModel

from app.core.ffmpeg_utils import ffmpeg_path

# YouTube occasionally throws up an anti-bot wall ("Sign in to confirm
# you're not a bot") that blocks plain, unauthenticated requests -- yt-dlp's
# own documented workaround is to read cookies from a browser the user is
# already logged into YouTube in. Tried in this order since Chrome/Edge's
# cookie DB is commonly locked while the browser is running (a known
# yt-dlp/Windows limitation) and Firefox's isn't.
_BOT_CHECK_SIGNATURE = "Sign in to confirm"
_COOKIE_BROWSER_FALLBACKS = ["firefox", "chrome", "edge", "brave", "vivaldi", "opera"]


class VideoInfo(BaseModel):
    title: str
    duration: float | None
    thumbnail_url: str | None
    available_resolutions: list[int]  # e.g. [1080, 720, 480, 360], descending


def _run_ydl(ydl_opts: dict, url: str, download: bool) -> tuple[yt_dlp.YoutubeDL, dict]:
    """Runs yt-dlp, transparently retrying with cookies read from a locally
    installed browser if YouTube responds with its bot-check wall -- real
    users already logged into YouTube in their own browser hit zero extra
    steps; only a genuinely blocked/logged-out machine reaches the final
    error below."""
    try:
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        with ydl:
            info = ydl.extract_info(url, download=download)
        return ydl, info
    except yt_dlp.utils.DownloadError as exc:
        if _BOT_CHECK_SIGNATURE not in str(exc):
            raise

    last_error: Exception = RuntimeError("no browser cookies were usable")
    for browser in _COOKIE_BROWSER_FALLBACKS:
        try:
            ydl = yt_dlp.YoutubeDL({**ydl_opts, "cookiesfrombrowser": (browser,)})
            with ydl:
                info = ydl.extract_info(url, download=download)
            return ydl, info
        except Exception as exc:  # noqa: BLE001 -- try the next browser
            last_error = exc
            continue

    raise RuntimeError(
        "YouTube is asking to verify you're not a bot, and no browser login could be used automatically. "
        "Make sure you're logged into YouTube in Chrome, Edge, or Firefox on this computer, close the browser "
        "(so its cookie file isn't locked), and try again."
    ) from last_error


def fetch_video_info(url: str) -> VideoInfo:
    """Raises on an invalid/private/unavailable URL (yt-dlp's own
    `DownloadError`) -- the caller reports that as a plain error message."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    _, info = _run_ydl(ydl_opts, url, download=False)

    heights = {
        int(fmt["height"])
        for fmt in info.get("formats", [])
        if fmt.get("vcodec") not in (None, "none") and fmt.get("height")
    }
    return VideoInfo(
        title=info.get("title") or url,
        duration=info.get("duration"),
        thumbnail_url=info.get("thumbnail"),
        available_resolutions=sorted(heights, reverse=True),
    )


def _make_progress_hook(
    on_progress: Callable[[float, str], None] | None, downloading_step: str, finishing_step: str
) -> Callable[[dict], None]:
    def hook(d: dict) -> None:
        if not on_progress:
            return
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                on_progress(min(1.0, downloaded / total), downloading_step)
        elif d.get("status") == "finished":
            on_progress(1.0, finishing_step)

    return hook


def _final_download_path(ydl: yt_dlp.YoutubeDL, info: dict, forced_ext: str) -> Path:
    downloads = info.get("requested_downloads") or []
    if downloads and downloads[0].get("filepath"):
        return Path(downloads[0]["filepath"])
    return Path(ydl.prepare_filename(info)).with_suffix(f".{forced_ext}")


def download_youtube_video(
    url: str,
    resolution: int,
    output_folder: str,
    on_progress: Callable[[float, str], None] | None = None,
) -> Path:
    """Downloads+merges the best video/audio streams at or below `resolution`
    (e.g. 1080 for "1080p"), returning the final file's path. Raises on
    failure -- the caller (a job runner) reports that through the job's
    error field, the same way every other pipeline stage does."""
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]",
        "outtmpl": str(Path(output_folder) / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_path(),
        "progress_hooks": [_make_progress_hook(on_progress, "Downloading video", "Merging video and audio")],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,  # we report progress via progress_hooks instead of yt-dlp's own stdout bar
    }

    ydl, info = _run_ydl(ydl_opts, url, download=True)
    return _final_download_path(ydl, info, "mp4")


def download_youtube_audio(
    url: str,
    output_folder: str,
    on_progress: Callable[[float, str], None] | None = None,
) -> Path:
    """Downloads the best available audio stream and transcodes it to MP3
    (via ffmpeg, same as the video path). Raises on failure, same
    conventions as `download_youtube_video`."""
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(output_folder) / "%(title)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "ffmpeg_location": ffmpeg_path(),
        "progress_hooks": [_make_progress_hook(on_progress, "Downloading audio", "Converting to MP3")],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
    }

    ydl, info = _run_ydl(ydl_opts, url, download=True)
    return _final_download_path(ydl, info, "mp3")

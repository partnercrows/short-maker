"""Copying a generated clip's files out of internal app storage to a
folder the user picked -- shared by the job runner's optional "also copy to
output folder" step and the on-demand Download action.

Also holds the Intro Frame export-time compositing step (see
`app/pipeline/intro.py` for the persisted `IntroFrame` model). Compositing
only ever produces a fresh output file here -- the clip's own
`rendered.mp4`/`video.mp4` masters are never touched, so subtitle timestamps
never need adjusting when an intro is toggled on or off.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.ffmpeg_utils import ffmpeg_path, probe_metadata

if TYPE_CHECKING:
    from app.pipeline.intro import IntroFrame

TARGET_WIDTH = 720
TARGET_HEIGHT = 1280


def safe_filename(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
    return cleaned[:80] or "clip"


def clip_base_name(clip) -> str:
    base_name = clip["id"]
    if clip["analysis_json"]:
        try:
            base_name = json.loads(clip["analysis_json"]).get("suggested_title") or base_name
        except json.JSONDecodeError:
            pass
    return safe_filename(base_name)


def copy_clip_to_folder(clip, video_path: str | Path, subtitle_path: str | None, destination_folder: str) -> Path:
    """Returns the path the video was copied to."""
    destination_dir = Path(destination_folder)
    destination_dir.mkdir(parents=True, exist_ok=True)

    base_name = clip_base_name(clip)
    destination_video = destination_dir / f"{base_name}.mp4"
    shutil.copyfile(video_path, destination_video)
    if subtitle_path:
        shutil.copyfile(subtitle_path, destination_dir / f"{base_name}.srt")
    return destination_video


def composite_intro_and_video(
    image_path: str | Path,
    video_path: str | Path,
    duration_seconds: float,
    output_path: str | Path,
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
) -> None:
    """Encodes a fresh video that shows `image_path` for `duration_seconds`
    then plays `video_path` (video+audio) in full. The still image gets a
    silent audio track generated via `anullsrc` so the two segments can be
    joined with ffmpeg's `concat` filter (which requires every segment to
    carry the same stream layout)."""
    metadata = probe_metadata(str(video_path))
    fps = metadata.fps or 30
    filter_complex = (
        f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[introv];"
        f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration_seconds}[introa];"
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[mainaudio];"
        "[introv][introa][1:v][mainaudio]concat=n=2:v=1:a=1[outv][outa]"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-loop",
            "1",
            "-t",
            str(duration_seconds),
            "-i",
            str(image_path),
            "-i",
            str(video_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def export_clip_to_folder(
    clip,
    video_path: str | Path,
    subtitle_path: str | None,
    destination_folder: str,
    intro: "IntroFrame | None" = None,
    intro_image_path: str | Path | None = None,
) -> Path:
    """Same as `copy_clip_to_folder`, but prepends the clip's Intro Frame
    image via a fresh ffmpeg encode when one is enabled and its image
    actually exists. Falls back to a plain copy otherwise -- a clip with no
    intro configured completes just as fast as before this feature existed.
    """
    if not intro or not intro.enabled or not intro_image_path or not Path(intro_image_path).is_file():
        return copy_clip_to_folder(clip, video_path, subtitle_path, destination_folder)

    destination_dir = Path(destination_folder)
    destination_dir.mkdir(parents=True, exist_ok=True)
    base_name = clip_base_name(clip)
    destination_video = destination_dir / f"{base_name}.mp4"
    composite_intro_and_video(intro_image_path, video_path, intro.duration_seconds, destination_video)
    if subtitle_path:
        shutil.copyfile(subtitle_path, destination_dir / f"{base_name}.srt")
    return destination_video

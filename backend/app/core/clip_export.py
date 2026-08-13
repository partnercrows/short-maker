"""Copying a generated clip's files out of internal app storage to a
folder the user picked -- shared by the job runner's optional "also copy to
output folder" step and the on-demand Download action.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


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

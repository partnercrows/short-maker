"""Turning the timeline into one video, and not doing it twice (PRD S28, S29, S46).

The rule that shapes this module: changing the audio, or the order of the
scenes, must not re-encode anything. So each scene is rendered once and keyed
by a fingerprint of the things that actually affect its pixels -- source,
time range, crop plan, output size. Audio mode and running order are
deliberately *not* in that key, which is why switching from muted to 20%
ambience is a one-second remux rather than a fresh render of the whole video.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from app.core.ffmpeg_utils import concat_videos
from app.pipeline.recipe.models import AudioMode
from app.pipeline.recipe.scene_render import SCENE_FPS, SCENE_HEIGHT, SCENE_NAME, SCENE_WIDTH, audio_filter_for, render_scene
from app.pipeline.reframe.models import ReframePlan

# Bump when a change to the renderer should invalidate everything cached.
RENDERER_VERSION = 1
FINGERPRINT_NAME = ".fingerprint"
CONCAT_NAME = "concat.txt"


def scene_fingerprint(
    source_video: str,
    start: float,
    end: float,
    plan: ReframePlan,
    target_width: int = SCENE_WIDTH,
    target_height: int = SCENE_HEIGHT,
    fps: int = SCENE_FPS,
) -> str:
    try:
        stat = os.stat(source_video)
        source_stat = [stat.st_size, int(stat.st_mtime)]
    except OSError:
        source_stat = [0, 0]
    payload = {
        "source": str(source_video),
        "source_stat": source_stat,
        "start": round(start, 3),
        "end": round(end, 3),
        "plan": json.loads(plan.model_dump_json()),
        "target": [target_width, target_height, fps],
        "renderer": RENDERER_VERSION,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:16]


def ensure_scene_rendered(
    source_video: str,
    *,
    scene_dir: Path,
    start: float,
    end: float,
    plan: ReframePlan,
    target_width: int = SCENE_WIDTH,
    target_height: int = SCENE_HEIGHT,
    fps: int = SCENE_FPS,
) -> tuple[Path, bool]:
    """Returns (scene file, rendered_now). A cache hit costs a file read."""
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scene_dir / SCENE_NAME
    fingerprint = scene_fingerprint(source_video, start, end, plan, target_width, target_height, fps)
    marker = scene_dir / FINGERPRINT_NAME

    if scene_path.is_file() and marker.is_file():
        try:
            if marker.read_text(encoding="utf-8").strip() == fingerprint:
                return scene_path, False
        except OSError:
            pass

    render_scene(
        source_video,
        start=start,
        duration=max(0.1, end - start),
        plan=plan,
        scene_dir=scene_dir,
        target_width=target_width,
        target_height=target_height,
        fps=fps,
    )
    marker.write_text(fingerprint, encoding="utf-8")
    return scene_path, True


def write_concat_file(scene_paths: list[Path], concat_path: Path) -> Path:
    """ffmpeg's concat list. Paths are forward-slashed and single-quoted,
    which is what its parser wants even on Windows."""
    concat_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for path in scene_paths:
        escaped = str(path).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat_path


def assemble(
    scene_paths: list[Path],
    output_path: Path,
    *,
    audio_mode: AudioMode = AudioMode.KEEP,
    volume_percent: int = 20,
    concat_path: Path | None = None,
) -> Path:
    if not scene_paths:
        raise ValueError("There are no scenes to assemble. Keep at least one scene in the timeline.")
    concat_file = write_concat_file(scene_paths, concat_path or output_path.parent / CONCAT_NAME)
    audio_filter, mute = audio_filter_for(audio_mode, volume_percent)
    concat_videos(str(concat_file), str(output_path), audio_filter=audio_filter, mute=mute)
    return output_path

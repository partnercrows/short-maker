"""Intro/Opening Frame: a static image prepended before a clip, only at
export time (never baked into `clip_dir/video.mp4`) -- see
`app/core/clip_export.py` for the actual compositing step.

Persisted the same way as `subtitle.json` (`app/pipeline/subtitle/models.py`):
a small JSON file under the clip's own directory, since it's a per-clip,
user-edited document, not a one-shot pipeline output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class IntroFrame(BaseModel):
    enabled: bool = False
    source: Literal["captured", "uploaded"] = "captured"
    source_timestamp: float | None = None  # only meaningful when source == "captured"
    duration_seconds: float = 2.0
    created_at: str


def load_intro_frame(path: str | Path) -> IntroFrame:
    return IntroFrame.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_intro_frame(path: str | Path, intro: IntroFrame) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(intro.model_dump_json(indent=2), encoding="utf-8")

"""Structured, editable subtitle data for Subtitle Studio (PRD S18-S22).

A `SubtitleDocument` is the single source of truth for a clip's subtitle
lines/style once Subtitle Studio has touched it -- persisted as JSON
(`load_document`/`save_document`) and only turned into pixels via
`ass_render.render_ass()` when the user explicitly renders/exports. Editing
it never re-runs Whisper, re-crops video, or touches `rendered.mp4`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SubtitlePosition(BaseModel):
    x: float = 360.0
    y: float = 1150.0


class SubtitleBackground(BaseModel):
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.6
    border_radius: float = 8.0
    padding: float = 12.0


class SubtitleStroke(BaseModel):
    enabled: bool = True
    color: str = "#000000"
    width: float = 2.0


class SubtitleShadow(BaseModel):
    enabled: bool = False
    color: str = "#000000"
    opacity: float = 0.5
    blur: float = 4.0
    offset_x: float = 2.0
    offset_y: float = 2.0


class SubtitleGlow(BaseModel):
    enabled: bool = False
    color: str = "#FFFFFF"
    opacity: float = 0.8
    blur: float = 8.0
    spread: float = 2.0


class SubtitleStyle(BaseModel):
    preset: str | None = None
    font_family: str = "Arial"
    font_size: int = 48
    font_weight: int = 700
    text_color: str = "#FFFFFF"
    position: SubtitlePosition = Field(default_factory=SubtitlePosition)
    alignment: Literal["left", "center", "right"] = "center"
    background: SubtitleBackground = Field(default_factory=SubtitleBackground)
    stroke: SubtitleStroke = Field(default_factory=SubtitleStroke)
    shadow: SubtitleShadow = Field(default_factory=SubtitleShadow)
    glow: SubtitleGlow = Field(default_factory=SubtitleGlow)
    uppercase: bool = False
    italic: bool = False
    # "karaoke" highlights the word currently being spoken (using each line's
    # per-word timestamps); falls back to "sentence" rendering for any line
    # whose `words` weren't captured (e.g. a manually-added line).
    display_mode: Literal["sentence", "karaoke"] = "sentence"
    highlight_color: str = "#FFE600"


class WordStyleOverride(BaseModel):
    """Reserved for word-level highlighting (e.g. making "SUBSCRIBE" stand
    out in its own color/weight/glow). No editor UI surfaces this yet --
    the field exists so today's per-word timing isn't lost by the time
    that UI is built (group_into_lines() would otherwise discard it)."""

    color: str | None = None
    weight: int | None = None
    background_color: str | None = None
    glow: bool | None = None


class SubtitleWord(BaseModel):
    text: str
    start: float
    end: float
    style: WordStyleOverride | None = None


class SubtitleDocumentLine(BaseModel):
    id: str
    start: float
    end: float
    text: str
    words: list[SubtitleWord] | None = None
    style: SubtitleStyle | None = None  # None = inherit the document's default_style


class SubtitleDocument(BaseModel):
    version: int = 1
    clip_id: str
    default_style: SubtitleStyle
    lines: list[SubtitleDocumentLine]
    updated_at: str


PRESETS: dict[str, SubtitleStyle] = {
    "penyorot": SubtitleStyle(
        preset="penyorot",
        font_family="Arial",
        font_size=52,
        font_weight=800,
        text_color="#FFEE00",
        alignment="center",
        position=SubtitlePosition(x=360, y=1150),
        background=SubtitleBackground(enabled=True, color="#000000", opacity=0.7, border_radius=10, padding=14),
        stroke=SubtitleStroke(enabled=True, color="#000000", width=3),
    ),
    "editorial": SubtitleStyle(
        preset="editorial",
        font_family="Georgia",
        font_size=46,
        font_weight=500,
        text_color="#FFFFFF",
        alignment="center",
        position=SubtitlePosition(x=360, y=1150),
        background=SubtitleBackground(enabled=False),
        stroke=SubtitleStroke(enabled=True, color="#000000", width=2),
        shadow=SubtitleShadow(enabled=True, color="#000000", opacity=0.5, blur=4, offset_x=1, offset_y=1),
    ),
    "bold_pop": SubtitleStyle(
        preset="bold_pop",
        font_family="Arial",
        font_size=56,
        font_weight=900,
        text_color="#FFFFFF",
        alignment="center",
        position=SubtitlePosition(x=360, y=1000),
        background=SubtitleBackground(enabled=False),
        stroke=SubtitleStroke(enabled=True, color="#FF2D55", width=4),
        glow=SubtitleGlow(enabled=True, color="#FF2D55", opacity=0.6, blur=10, spread=3),
    ),
    "newsroom": SubtitleStyle(
        preset="newsroom",
        font_family="Arial",
        font_size=42,
        font_weight=600,
        text_color="#FFFFFF",
        alignment="left",
        position=SubtitlePosition(x=60, y=1180),
        background=SubtitleBackground(enabled=True, color="#CC0000", opacity=1.0, border_radius=0, padding=10),
        stroke=SubtitleStroke(enabled=False),
    ),
}

DEFAULT_PRESET = "editorial"


def load_document(path: str | Path) -> SubtitleDocument:
    return SubtitleDocument.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_document(path: str | Path, document: SubtitleDocument) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(indent=2), encoding="utf-8")

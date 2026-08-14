"""Subtitle generation/rendering (PRD S18-S22).

Two burn-in paths coexist:
- `burn_subtitles()` -- the original default-style-only SRT burn, kept for
  backward compatibility with anything still calling it directly.
- `burn_ass_subtitles()` -- the Subtitle Studio path (PRD S20): a
  `SubtitleDocument` (see `models.py`) is rendered to `.ass` via
  `ass_render.render_ass()`, giving per-line style, position and effects
  that plain SRT + a single global `force_style` can't express.

Subtitle regeneration staying independent of clip regeneration (S18) is why
this lives in its own module, called from the clip-generate flow rather
than baked into rendering itself -- editing/re-rendering a `SubtitleDocument`
never re-runs Whisper, Active Speaker, or the crop pass.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.ffmpeg_utils import ffmpeg_path
from app.pipeline.subtitle.models import (
    DEFAULT_PRESET,
    PRESETS,
    SubtitleDocument,
    SubtitleDocumentLine,
    SubtitleWord,
    load_document,
    save_document,
)
from app.pipeline.transcribe import Word

MAX_WORDS_PER_LINE = 7
MAX_LINE_DURATION = 4.0


class SubtitleLine:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start = start
        self.end = end
        self.text = text


def slice_words(words: list[Word], clip_start: float, clip_end: float) -> list[Word]:
    """Words within [clip_start, clip_end], with timestamps shifted to be
    relative to the clip's own start (0-based, matching the clip file)."""
    return [
        Word(text=w.text, start=w.start - clip_start, end=w.end - clip_start)
        for w in words
        if clip_start <= w.start < clip_end
    ]


def load_clip_words(transcript_path: str | Path, clip_start: float, clip_end: float) -> list[Word]:
    """Reads the full-project transcript.json (written once during analyze)
    and returns just this clip's words, clip-relative -- the shared first
    step behind both `run_generate_job`'s legacy checkbox burn and Subtitle
    Studio's initial-document seeding."""
    data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    words = [Word(**w) for w in data["words"]]
    return slice_words(words, clip_start, clip_end)


def _chunk_words(words: list[Word], max_words_per_line: int, max_line_duration: float) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        would_exceed_duration = bool(current) and (word.end - current[0].start) > max_line_duration
        would_exceed_count = len(current) >= max_words_per_line
        if would_exceed_duration or would_exceed_count:
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def group_into_lines(
    words: list[Word], max_words_per_line: int = MAX_WORDS_PER_LINE, max_line_duration: float = MAX_LINE_DURATION
) -> list[SubtitleLine]:
    return [
        SubtitleLine(start=chunk[0].start, end=chunk[-1].end, text=" ".join(w.text for w in chunk))
        for chunk in _chunk_words(words, max_words_per_line, max_line_duration)
    ]


def build_initial_document(clip_id: str, words: list[Word], preset: str = DEFAULT_PRESET) -> SubtitleDocument:
    """Seeds a `SubtitleDocument` from a clip's (already clip-relative, via
    `slice_words`) word timestamps -- the starting point Subtitle Studio
    opens with before any user edits."""
    chunks = _chunk_words(words, MAX_WORDS_PER_LINE, MAX_LINE_DURATION)
    lines = [
        SubtitleDocumentLine(
            id=str(uuid.uuid4()),
            start=chunk[0].start,
            end=chunk[-1].end,
            text=" ".join(w.text for w in chunk),
            words=[SubtitleWord(text=w.text, start=w.start, end=w.end) for w in chunk],
        )
        for chunk in chunks
    ]
    return SubtitleDocument(
        clip_id=clip_id,
        default_style=PRESETS[preset].model_copy(deep=True),
        lines=lines,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, remainder = divmod(remainder, 60)
    secs, millis = divmod(remainder, 1)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d},{int(millis * 1000):03d}"


def lines_to_srt(lines: list[SubtitleLine]) -> str:
    blocks = []
    for i, line in enumerate(lines, start=1):
        blocks.append(f"{i}\n{_srt_timestamp(line.start)} --> {_srt_timestamp(line.end)}\n{line.text}\n")
    return "\n".join(blocks)


def _escape_path_for_filter(path: str) -> str:
    # ffmpeg's filter-graph mini-language treats ':' and '\' specially,
    # which collides with Windows drive letters and path separators.
    return path.replace("\\", "/").replace(":", "\\:")


def burn_subtitles(video_path: str, srt_path: str, output_path: str) -> None:
    escaped = _escape_path_for_filter(srt_path)
    style = "FontName=Arial,FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,BorderStyle=1,Outline=2,Alignment=2"
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-i",
            video_path,
            "-vf",
            f"subtitles='{escaped}':force_style='{style}'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            output_path,
        ],
        check=True,
        capture_output=True,
    )


def burn_ass_subtitles(video_path: str, ass_path: str, output_path: str) -> None:
    """Like `burn_subtitles()`, but for a styled `.ass` file (produced by
    `ass_render.render_ass()`) instead of a plain `.srt` -- no `force_style`
    needed since the style is already baked into the .ass file itself."""
    escaped = _escape_path_for_filter(ass_path)
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-i",
            video_path,
            "-vf",
            f"ass='{escaped}'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "copy",
            output_path,
        ],
        check=True,
        capture_output=True,
    )

"""Subtitle generation/rendering (PRD S18-S22).

This pass implements a *default-style-only* SRT burn-in for generated
clips (grouping Whisper word timestamps into short lines, no user-facing
style controls) -- the Canva-style editable styling (fonts/colors/
animations/position, PRD S20) is Phase 3 UI work, still `SubtitleRenderer`
below. Subtitle regeneration staying independent of clip regeneration
(S18) is why this lives in its own module, called from the clip-generate
flow rather than baked into rendering itself.
"""

from __future__ import annotations

import subprocess

from app.core.ffmpeg_utils import ffmpeg_path
from app.pipeline.transcribe import Word

MAX_WORDS_PER_LINE = 7
MAX_LINE_DURATION = 4.0


class SubtitleRenderer:
    def render_ass(self, transcript_json: str, style: dict) -> str:
        raise NotImplementedError("Styled ASS rendering lands with the Phase 3 subtitle editor.")


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


def group_into_lines(
    words: list[Word], max_words_per_line: int = MAX_WORDS_PER_LINE, max_line_duration: float = MAX_LINE_DURATION
) -> list[SubtitleLine]:
    lines: list[SubtitleLine] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            lines.append(SubtitleLine(start=current[0].start, end=current[-1].end, text=" ".join(w.text for w in current)))

    for word in words:
        would_exceed_duration = current and (word.end - current[0].start) > max_line_duration
        would_exceed_count = len(current) >= max_words_per_line
        if would_exceed_duration or would_exceed_count:
            flush()
            current = []
        current.append(word)
    flush()
    return lines


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

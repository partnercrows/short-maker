"""SubtitleStyle -> .ass (Advanced SubStation Alpha) rendering.

ASS is the target format (not plain SRT) specifically because it supports
per-event position (`\\pos`), alignment (`\\an`) and blur (`\\blur`) override
tags -- which is what lets each subtitle line carry its own position/style
instead of one global `force_style` for the whole clip.

Known, documented approximations (not silently wrong): ASS has no font
weight axis (approximated as Bold on/off), no background border-radius (the
box always renders sharp-cornered), no independent shadow blur or X/Y
offsets (`Shadow` is a single scalar), and no native glow -- glow is
approximated with a second, blurred, lower-layer copy of the same line.
"""

from __future__ import annotations

from app.pipeline.subtitle.models import SubtitleDocument, SubtitleDocumentLine, SubtitleStyle

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 1280

_TRANSPARENT = "&H00000000"


def _hex_to_ass_color(hex_color: str, opacity: float = 1.0) -> str:
    """'#RRGGBB' + opacity (0=transparent..1=opaque) -> ASS's '&HAABBGGRR'."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    alpha = format(max(0, min(255, round((1 - opacity) * 255))), "02X")
    return f"&H{alpha}{b}{g}{r}".upper()


def _alignment_code(alignment: str) -> int:
    # Column from text alignment; always middle-row-anchored (4/5/6) so
    # `\pos`'s y coordinate is the vertical center of the text, matching
    # what a user dragging a subtitle box in a preview would expect --
    # independent of ASS's usual bottom/middle/top *thirds* convention.
    column = {"left": 1, "center": 2, "right": 3}.get(alignment, 2)
    return column + 3


def _ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, remainder = divmod(remainder, 60)
    secs, centis = divmod(remainder, 1)
    return f"{int(hours)}:{int(minutes):02d}:{int(secs):02d}.{int(centis * 100):02d}"


def _style_line(name: str, style: SubtitleStyle) -> str:
    bold = -1 if style.font_weight >= 600 else 0
    italic = -1 if style.italic else 0
    primary = _hex_to_ass_color(style.text_color)

    if style.background.enabled:
        # BorderStyle=3 (opaque box) and stroke can't both be expressed via
        # the same field in classic ASS -- background wins when enabled;
        # padding approximates via Outline, which inflates the box in this mode.
        border_style = 3
        outline = max(0.0, style.background.padding) / 4
        outline_colour = _hex_to_ass_color(style.background.color, style.background.opacity)
        back_colour = outline_colour
        shadow = 0.0
    else:
        border_style = 1
        outline = style.stroke.width if style.stroke.enabled else 0.0
        outline_colour = _hex_to_ass_color(style.stroke.color) if style.stroke.enabled else _TRANSPARENT
        back_colour = (
            _hex_to_ass_color(style.shadow.color, style.shadow.opacity) if style.shadow.enabled else _TRANSPARENT
        )
        shadow = max(abs(style.shadow.offset_x), abs(style.shadow.offset_y)) if style.shadow.enabled else 0.0

    return (
        f"Style: {name},{style.font_family},{style.font_size},{primary},{primary},"
        f"{outline_colour},{back_colour},{bold},{italic},0,0,100,100,0,0,"
        f"{border_style},{outline},{shadow},5,0,0,0,1"
    )


def _line_text(line: SubtitleDocumentLine, style: SubtitleStyle) -> str:
    text = line.text.upper() if style.uppercase else line.text
    return text.replace("\n", "\\N")


def _sentence_dialogue_events(line: SubtitleDocumentLine, style: SubtitleStyle, style_name: str) -> list[str]:
    an = _alignment_code(style.alignment)
    pos = f"\\an{an}\\pos({style.position.x:.0f},{style.position.y:.0f})"
    start = _ass_timestamp(line.start)
    end = _ass_timestamp(line.end)
    text = _line_text(line, style)

    events = []
    if style.glow.enabled:
        glow_colour = _hex_to_ass_color(style.glow.color, style.glow.opacity)
        glow_tags = f"{{{pos}\\c{glow_colour}\\bord{style.glow.spread}\\blur{style.glow.blur}}}"
        events.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{glow_tags}{text}")
    events.append(f"Dialogue: 1,{start},{end},{style_name},,0,0,0,,{{{pos}}}{text}")
    return events


def _karaoke_dialogue_events(line: SubtitleDocumentLine, style: SubtitleStyle, style_name: str) -> list[str]:
    """One Dialogue event per word, each spanning [this word's start, the
    next word's start] (or the line's own end for the last word), showing
    the full line with only the active word wrapped in a `\\c` colour
    override -- the same technique as ASS glow (models.py's `SubtitleGlow`),
    just applied per-word instead of per-line."""
    if not line.words:
        # No per-word timestamps (e.g. a manually-added line) -- there's
        # nothing to highlight word-by-word, so render it as a sentence.
        return _sentence_dialogue_events(line, style, style_name)

    an = _alignment_code(style.alignment)
    pos = f"\\an{an}\\pos({style.position.x:.0f},{style.position.y:.0f})"
    primary = _hex_to_ass_color(style.text_color)
    highlight = _hex_to_ass_color(style.highlight_color)
    words = line.words
    num_words = len(words)

    events = []
    for i, word in enumerate(words):
        w_start = word.start
        w_end = words[i + 1].start if i < num_words - 1 else line.end
        if w_end <= w_start:
            continue
        parts = []
        for j, w in enumerate(words):
            word_text = w.text.upper() if style.uppercase else w.text
            parts.append(f"{{\\c{highlight}}}{word_text}{{\\c{primary}}}" if j == i else word_text)
        text = " ".join(parts)
        start_ts = _ass_timestamp(w_start)
        end_ts = _ass_timestamp(w_end)
        events.append(f"Dialogue: 0,{start_ts},{end_ts},{style_name},,0,0,0,,{{{pos}}}{text}")
    return events


def _dialogue_events(line: SubtitleDocumentLine, style: SubtitleStyle, style_name: str) -> list[str]:
    if style.display_mode == "karaoke":
        return _karaoke_dialogue_events(line, style, style_name)
    return _sentence_dialogue_events(line, style, style_name)


def render_ass(document: SubtitleDocument) -> str:
    """Renders a `SubtitleDocument` to full `.ass` file text. One `[V4+
    Styles]` line is emitted per distinct style object in use (the clip
    default plus any per-line overrides); every `Dialogue` event still
    carries its own `\\pos`/`\\an` override so per-line position/alignment
    works even when several lines share one named style."""
    style_names: dict[int, str] = {}
    styles_in_order: list[tuple[str, SubtitleStyle]] = []

    def _style_name_for(style: SubtitleStyle) -> str:
        key = id(style)
        if key not in style_names:
            name = "Default" if not styles_in_order else f"Style{len(styles_in_order)}"
            style_names[key] = name
            styles_in_order.append((name, style))
        return style_names[key]

    default_name = _style_name_for(document.default_style)

    dialogue_lines: list[str] = []
    for line in document.lines:
        style = line.style or document.default_style
        style_name = _style_name_for(style) if line.style else default_name
        dialogue_lines.extend(_dialogue_events(line, style, style_name))

    style_block = "\n".join(_style_line(name, style) for name, style in styles_in_order)

    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {CANVAS_WIDTH}\n"
        f"PlayResY: {CANVAS_HEIGHT}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_block}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        + "\n".join(dialogue_lines)
        + "\n"
    )

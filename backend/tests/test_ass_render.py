from app.pipeline.subtitle.ass_render import _alignment_code, _ass_timestamp, _hex_to_ass_color, render_ass
from app.pipeline.subtitle.models import PRESETS, SubtitleDocument, SubtitleDocumentLine, SubtitleStyle, SubtitleWord


def _make_document(**line_kwargs) -> SubtitleDocument:
    line = SubtitleDocumentLine(id="l1", start=0.0, end=2.0, text="Hello world", **line_kwargs)
    return SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")


def test_hex_to_ass_color_opaque_white():
    assert _hex_to_ass_color("#FFFFFF", opacity=1.0) == "&H00FFFFFF"


def test_hex_to_ass_color_reverses_to_bgr():
    # pure red (#FF0000) -> BGR bytes 00 00 FF
    assert _hex_to_ass_color("#FF0000", opacity=1.0) == "&H000000FF"


def test_hex_to_ass_color_half_transparent():
    assert _hex_to_ass_color("#000000", opacity=0.5) == "&H80000000"


def test_alignment_code_maps_left_center_right_to_middle_row():
    assert _alignment_code("left") == 4
    assert _alignment_code("center") == 5
    assert _alignment_code("right") == 6


def test_ass_timestamp_format():
    assert _ass_timestamp(0.0) == "0:00:00.00"
    assert _ass_timestamp(65.25) == "0:01:05.25"


def test_render_ass_includes_script_header_and_dialogue_text():
    doc = _make_document()
    ass = render_ass(doc)

    assert "[Script Info]" in ass
    assert "PlayResX: 720" in ass
    assert "PlayResY: 1280" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "Hello world" in ass
    assert "\\pos(360,1150)" in ass  # editorial preset's default position


def test_render_ass_glow_adds_extra_dialogue_layer():
    glow_style = PRESETS["bold_pop"]  # has glow enabled
    line = SubtitleDocumentLine(id="l1", start=0.0, end=1.0, text="Pop", style=glow_style)
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    dialogue_count = ass.count("Dialogue: ")
    assert dialogue_count == 2  # one glow layer + one real text layer
    assert "\\blur" in ass


def test_render_ass_no_glow_by_default_single_dialogue_per_line():
    doc = _make_document()  # editorial preset has glow disabled
    ass = render_ass(doc)
    assert ass.count("Dialogue: ") == 1


def test_render_ass_background_uses_border_style_3():
    style = SubtitleStyle()
    style.background.enabled = True
    line = SubtitleDocumentLine(id="l1", start=0.0, end=1.0, text="Boxed", style=style)
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    # two styles now exist: the document default + this line's override
    assert ass.count("Style: ") == 2
    style_lines = [line for line in ass.splitlines() if line.startswith("Style: ") and "Style1" in line]
    assert style_lines
    fields = style_lines[0].split(",")
    border_style_index = 15  # per the Format: header ordering (Name..Angle is 0-14, BorderStyle is next)
    assert fields[border_style_index] == "3"


def test_style_line_italic_field_set_when_enabled():
    style = SubtitleStyle()
    style.italic = True
    line = SubtitleDocumentLine(id="l1", start=0.0, end=1.0, text="Slanted", style=style)
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    style_lines = [line for line in ass.splitlines() if line.startswith("Style: ") and "Style1" in line]
    fields = style_lines[0].split(",")
    italic_index = 8  # Name..BackColour is 0-6, Bold is 7, Italic is 8
    assert fields[italic_index] == "-1"


def test_uppercase_transforms_dialogue_text():
    style = SubtitleStyle()
    style.uppercase = True
    line = SubtitleDocumentLine(id="l1", start=0.0, end=1.0, text="shout this", style=style)
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    assert "SHOUT THIS" in ass
    assert "shout this" not in ass


def _make_karaoke_line() -> SubtitleDocumentLine:
    style = SubtitleStyle()
    style.display_mode = "karaoke"
    style.highlight_color = "#FFE600"
    return SubtitleDocumentLine(
        id="l1",
        start=0.0,
        end=1.5,
        text="one two three",
        words=[
            SubtitleWord(text="one", start=0.0, end=0.4),
            SubtitleWord(text="two", start=0.5, end=0.9),
            SubtitleWord(text="three", start=1.0, end=1.5),
        ],
        style=style,
    )


def test_karaoke_mode_emits_one_dialogue_event_per_word():
    line = _make_karaoke_line()
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    assert ass.count("Dialogue: ") == 3


def test_karaoke_mode_highlights_active_word_and_shows_full_sentence_each_event():
    line = _make_karaoke_line()
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue: ")]
    assert len(dialogue_lines) == 3
    # Every event shows the full sentence (not just the active word).
    for d in dialogue_lines:
        assert "one" in d and "two" in d and "three" in d
    # The highlight colour override tag appears in each event.
    highlight_ass_colour = _hex_to_ass_color("#FFE600")
    for d in dialogue_lines:
        assert f"\\c{highlight_ass_colour}" in d


def test_karaoke_mode_word_timing_spans_to_next_word_start():
    line = _make_karaoke_line()
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue: ")]
    # First word: start=0.0, ends at second word's start (0.5), not its own raw end (0.4).
    first_start, first_end = dialogue_lines[0].split(",")[1:3]
    assert first_start == _ass_timestamp(0.0)
    assert first_end == _ass_timestamp(0.5)
    # Last word: ends at the line's own end (1.5).
    last_start, last_end = dialogue_lines[2].split(",")[1:3]
    assert last_start == _ass_timestamp(1.0)
    assert last_end == _ass_timestamp(1.5)


def test_karaoke_mode_falls_back_to_sentence_when_no_words():
    style = SubtitleStyle()
    style.display_mode = "karaoke"
    line = SubtitleDocumentLine(id="l1", start=0.0, end=1.0, text="no word data", style=style, words=None)
    doc = SubtitleDocument(clip_id="clip-1", default_style=PRESETS["editorial"], lines=[line], updated_at="now")

    ass = render_ass(doc)
    assert ass.count("Dialogue: ") == 1
    assert "no word data" in ass

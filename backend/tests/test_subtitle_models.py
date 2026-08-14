from app.pipeline.subtitle import build_initial_document
from app.pipeline.subtitle.models import (
    DEFAULT_PRESET,
    PRESETS,
    SubtitleDocument,
    SubtitleDocumentLine,
    SubtitleStyle,
    load_document,
    save_document,
)
from app.pipeline.transcribe import Word


def test_presets_cover_all_four_named_styles():
    assert set(PRESETS.keys()) == {"penyorot", "editorial", "bold_pop", "newsroom"}
    for name, style in PRESETS.items():
        assert style.preset == name


def test_default_preset_is_a_real_preset():
    assert DEFAULT_PRESET in PRESETS


def test_build_initial_document_groups_words_and_retains_word_timing():
    words = [Word(text=str(i), start=float(i), end=i + 0.5) for i in range(10)]
    doc = build_initial_document("clip-1", words)

    assert doc.clip_id == "clip-1"
    assert doc.default_style.preset == DEFAULT_PRESET
    assert len(doc.lines) > 0
    # Every line keeps its underlying per-word timing (for future word-highlight use).
    for line in doc.lines:
        assert line.words is not None
        assert " ".join(w.text for w in line.words) == line.text
        assert line.style is None  # inherits document default
    # ids are unique
    assert len({line.id for line in doc.lines}) == len(doc.lines)


def test_save_and_load_document_roundtrip(tmp_path):
    words = [Word(text="hello", start=0.0, end=0.5), Word(text="world", start=0.6, end=1.0)]
    doc = build_initial_document("clip-2", words)

    path = tmp_path / "subtitle.json"
    save_document(path, doc)
    loaded = load_document(path)

    assert loaded == doc


def test_line_level_style_override_is_optional():
    line = SubtitleDocumentLine(id="a", start=0, end=1, text="hi")
    assert line.style is None
    line_with_override = SubtitleDocumentLine(id="b", start=0, end=1, text="hi", style=SubtitleStyle())
    assert line_with_override.style is not None

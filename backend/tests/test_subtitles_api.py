from __future__ import annotations

import json

import pytest

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.api.subtitles import (
    ApplyStyleRequest,
    CorrectSubtitlesRequest,
    apply_subtitle_style,
    correct_subtitles,
    get_subtitle_document,
    save_subtitle_document,
)
from app.core.config import get_settings
from app.db.connection import get_connection, init_db
from app.pipeline.subtitle.models import PRESETS, SubtitleDocument, SubtitleDocumentLine, SubtitleStyle
from fastapi import HTTPException

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")


def _make_project_and_clip(project_id: str, clip_id: str, start: float, end: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
            "VALUES (?, 'p', 'v.mp4', 'queued', 'now', 'now')",
            (project_id,),
        )
        conn.execute(
            """
            INSERT INTO clips (id, project_id, start_time, end_time, duration, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'completed', 'now', 'now')
            """,
            (clip_id, project_id, start, end, end - start),
        )
        conn.commit()


def _write_transcript(project_id: str) -> None:
    settings = get_settings()
    analysis_dir = settings.project_analysis_dir(project_id)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    words = [{"text": str(i), "start": float(i), "end": i + 0.4} for i in range(10)]
    (analysis_dir / "transcript.json").write_text(json.dumps({"words": words, "segments": [], "text": ""}), encoding="utf-8")


def test_get_subtitle_document_lazily_creates_and_reports_needs_rebuild():
    init_db()
    _make_project_and_clip("proj-1", "clip-1", 0.0, 5.0)
    _write_transcript("proj-1")

    response = get_subtitle_document("clip-1")

    assert response.needs_rebuild is True  # no rendered.mp4 exists
    assert response.rendered_video_path is None
    assert len(response.document.lines) > 0
    assert response.document.default_style.preset is not None

    with get_connection() as conn:
        row = conn.execute("SELECT subtitle_json_path FROM clips WHERE id = ?", ("clip-1",)).fetchone()
    assert row["subtitle_json_path"] is not None


def test_get_subtitle_document_needs_rebuild_false_when_rendered_exists():
    init_db()
    _make_project_and_clip("proj-2", "clip-2", 0.0, 5.0)
    _write_transcript("proj-2")

    settings = get_settings()
    rendered_path = settings.clip_rendered_path("proj-2", "clip-2")
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_bytes(b"fake video")

    response = get_subtitle_document("clip-2")
    assert response.needs_rebuild is False
    assert response.rendered_video_path == str(rendered_path)


def test_get_subtitle_document_404_for_missing_clip():
    init_db()
    with pytest.raises(HTTPException) as exc_info:
        get_subtitle_document("does-not-exist")
    assert exc_info.value.status_code == 404


def test_save_subtitle_document_rejects_duplicate_ids():
    init_db()
    _make_project_and_clip("proj-3", "clip-3", 0.0, 5.0)
    doc = SubtitleDocument(
        clip_id="clip-3",
        default_style=PRESETS["editorial"],
        lines=[
            SubtitleDocumentLine(id="dup", start=0, end=1, text="a"),
            SubtitleDocumentLine(id="dup", start=1, end=2, text="b"),
        ],
        updated_at="now",
    )
    with pytest.raises(HTTPException) as exc_info:
        save_subtitle_document("clip-3", doc)
    assert exc_info.value.status_code == 400


def test_save_subtitle_document_rejects_bad_timing():
    init_db()
    _make_project_and_clip("proj-4", "clip-4", 0.0, 5.0)
    doc = SubtitleDocument(
        clip_id="clip-4",
        default_style=PRESETS["editorial"],
        lines=[SubtitleDocumentLine(id="a", start=2, end=1, text="backwards")],
        updated_at="now",
    )
    with pytest.raises(HTTPException) as exc_info:
        save_subtitle_document("clip-4", doc)
    assert exc_info.value.status_code == 400


def test_save_subtitle_document_sorts_lines_by_start():
    init_db()
    _make_project_and_clip("proj-5", "clip-5", 0.0, 5.0)
    doc = SubtitleDocument(
        clip_id="clip-5",
        default_style=PRESETS["editorial"],
        lines=[
            SubtitleDocumentLine(id="second", start=2, end=3, text="b"),
            SubtitleDocumentLine(id="first", start=0, end=1, text="a"),
        ],
        updated_at="now",
    )
    saved = save_subtitle_document("clip-5", doc)
    assert [line.id for line in saved.lines] == ["first", "second"]


def test_apply_style_scope_clip_updates_default_style():
    init_db()
    _make_project_and_clip("proj-6", "clip-6", 0.0, 5.0)
    _write_transcript("proj-6")
    get_subtitle_document("clip-6")  # seed the document

    new_style = SubtitleStyle(preset="bold_pop")
    result = apply_subtitle_style("clip-6", ApplyStyleRequest(scope="clip", style=new_style))
    assert result.default_style.preset == "bold_pop"


def test_apply_style_scope_lines_sets_per_line_override():
    init_db()
    _make_project_and_clip("proj-7", "clip-7", 0.0, 5.0)
    _write_transcript("proj-7")
    seeded = get_subtitle_document("clip-7").document
    target_id = seeded.lines[0].id

    new_style = SubtitleStyle(preset="newsroom")
    result = apply_subtitle_style("clip-7", ApplyStyleRequest(scope="lines", line_ids=[target_id], style=new_style))

    assert result.lines[0].style is not None
    assert result.lines[0].style.preset == "newsroom"
    assert result.lines[1].style is None  # untouched


def test_apply_style_unknown_line_id_404s():
    init_db()
    _make_project_and_clip("proj-8", "clip-8", 0.0, 5.0)
    _write_transcript("proj-8")
    get_subtitle_document("clip-8")

    with pytest.raises(HTTPException) as exc_info:
        apply_subtitle_style("clip-8", ApplyStyleRequest(scope="lines", line_ids=["nope"], style=SubtitleStyle()))
    assert exc_info.value.status_code == 404


def test_correct_subtitles_returns_suggestions_without_persisting(monkeypatch):
    init_db()
    _make_project_and_clip("proj-9", "clip-9", 0.0, 5.0)
    _write_transcript("proj-9")
    seeded = get_subtitle_document("clip-9").document
    target_id = seeded.lines[0].id
    original_text = seeded.lines[0].text

    fake_response = json.dumps([{"id": target_id, "corrected_text": "Fixed text."}])
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: fake_response)

    result = correct_subtitles("clip-9", CorrectSubtitlesRequest(provider=_PROVIDER))

    assert any(c.id == target_id and c.corrected_text == "Fixed text." for c in result.corrections)
    # Preview-only: the persisted document is untouched.
    reloaded = get_subtitle_document("clip-9").document
    assert reloaded.lines[0].text == original_text


def test_correct_subtitles_404_when_no_document_yet():
    init_db()
    _make_project_and_clip("proj-10", "clip-10", 0.0, 5.0)

    with pytest.raises(HTTPException) as exc_info:
        correct_subtitles("clip-10", CorrectSubtitlesRequest(provider=_PROVIDER))
    assert exc_info.value.status_code == 404


def test_correct_subtitles_404_for_unknown_line_id():
    init_db()
    _make_project_and_clip("proj-11", "clip-11", 0.0, 5.0)
    _write_transcript("proj-11")
    get_subtitle_document("clip-11")

    with pytest.raises(HTTPException) as exc_info:
        correct_subtitles("clip-11", CorrectSubtitlesRequest(provider=_PROVIDER, line_ids=["nope"]))
    assert exc_info.value.status_code == 404


def test_correct_subtitles_surfaces_ai_errors_as_400(monkeypatch):
    init_db()
    _make_project_and_clip("proj-12", "clip-12", 0.0, 5.0)
    _write_transcript("proj-12")
    get_subtitle_document("clip-12")

    def boom(*a, **k):
        raise RuntimeError("provider is unreachable")

    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", boom)

    with pytest.raises(HTTPException) as exc_info:
        correct_subtitles("clip-12", CorrectSubtitlesRequest(provider=_PROVIDER))
    assert exc_info.value.status_code == 400
    assert "provider is unreachable" in exc_info.value.detail

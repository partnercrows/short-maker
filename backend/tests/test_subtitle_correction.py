from __future__ import annotations

import json

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.pipeline.subtitle.correction import build_correction_prompt, correct_subtitle_lines
from app.pipeline.subtitle.models import SubtitleDocumentLine

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")


def _make_lines() -> list[SubtitleDocumentLine]:
    return [
        SubtitleDocumentLine(id="a", start=0.0, end=1.0, text="helo wrold"),
        SubtitleDocumentLine(id="b", start=1.0, end=2.0, text="this is fine"),
    ]


def test_build_correction_prompt_includes_line_ids_and_text():
    system_prompt, user_prompt = build_correction_prompt(_make_lines())
    assert "JSON array" in system_prompt
    assert '"id": "a"' in user_prompt
    assert "helo wrold" in user_prompt


def test_correct_subtitle_lines_parses_valid_response(monkeypatch):
    response = json.dumps([{"id": "a", "corrected_text": "hello world"}, {"id": "b", "corrected_text": "this is fine"}])
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: response)

    corrections = correct_subtitle_lines(_PROVIDER, _make_lines())

    assert len(corrections) == 2
    assert {c.id: c.corrected_text for c in corrections} == {"a": "hello world", "b": "this is fine"}


def test_correct_subtitle_lines_parses_fenced_json(monkeypatch):
    response = f"```json\n{json.dumps([{'id': 'a', 'corrected_text': 'hello world'}])}\n```"
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: response)

    corrections = correct_subtitle_lines(_PROVIDER, _make_lines())

    assert len(corrections) == 1
    assert corrections[0].corrected_text == "hello world"


def test_correct_subtitle_lines_ignores_unknown_ids(monkeypatch):
    response = json.dumps([{"id": "a", "corrected_text": "hello world"}, {"id": "does-not-exist", "corrected_text": "x"}])
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: response)

    corrections = correct_subtitle_lines(_PROVIDER, _make_lines())

    assert len(corrections) == 1
    assert corrections[0].id == "a"


def test_correct_subtitle_lines_ignores_malformed_items(monkeypatch):
    response = json.dumps([{"id": "a", "corrected_text": "hello world"}, {"id": "b"}, "not-a-dict", 42])
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: response)

    corrections = correct_subtitle_lines(_PROVIDER, _make_lines())

    assert len(corrections) == 1
    assert corrections[0].id == "a"


def test_correct_subtitle_lines_raises_when_response_is_not_a_list(monkeypatch):
    response = json.dumps({"id": "a", "corrected_text": "hello world"})
    monkeypatch.setattr("app.pipeline.subtitle.correction.complete_chat", lambda *a, **k: response)

    try:
        correct_subtitle_lines(_PROVIDER, _make_lines())
        assert False, "expected ValueError"
    except ValueError:
        pass

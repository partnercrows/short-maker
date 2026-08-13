from __future__ import annotations

import json

import pytest

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.api.social_kit import _build_clip_summary, _generate_and_save, _get_clip_or_404
from app.db.connection import get_connection, init_db
from app.pipeline.social_kit import generate_social_kit

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")

_FAKE_RESPONSE_V1 = json.dumps(
    {
        "titles": [{"title": "Judul A", "score": 90}, {"title": "Judul B", "score": 80}, {"title": "Judul C", "score": 70}],
        "description": "Deskripsi versi 1",
        "hashtags": ["#tag1", "tag2"],
        "thumbnail_idea": "Ide thumbnail v1",
        "thumbnail_prompt": "Prompt thumbnail v1",
    }
)

_FAKE_RESPONSE_V2 = json.dumps(
    {
        "titles": [{"title": "Judul baru", "score": 95}, {"title": "B", "score": 81}, {"title": "C", "score": 71}],
        "description": "Deskripsi versi 2",
        "hashtags": ["#tagbaru"],
        "thumbnail_idea": "Ide thumbnail v2",
        "thumbnail_prompt": "Prompt thumbnail v2",
    }
)


def _make_clip(clip_id: str, *, analysis_json: str | None, transcript_json: str | None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
            "VALUES ('proj-1', 'p', 'v.mp4', 'queued', 'now', 'now')"
        )
        conn.execute(
            """
            INSERT INTO clips (id, project_id, start_time, end_time, duration, score,
                analysis_json, transcript_json, status, created_at, updated_at)
            VALUES (?, 'proj-1', 0, 10, 10, 90, ?, ?, 'completed', 'now', 'now')
            """,
            (clip_id, analysis_json, transcript_json),
        )
        conn.commit()


def test_build_clip_summary_uses_analysis_and_transcript():
    init_db()
    analysis = json.dumps({"suggested_title": "Judul", "reason": "Karena bagus"})
    transcript = json.dumps([{"text": "halo"}, {"text": "dunia"}])
    _make_clip("clip-1", analysis_json=analysis, transcript_json=transcript)

    summary = _build_clip_summary(_get_clip_or_404("clip-1"))

    assert "Judul" in summary
    assert "Karena bagus" in summary
    assert "halo dunia" in summary


def test_build_clip_summary_raises_when_clip_has_nothing():
    init_db()
    _make_clip("clip-2", analysis_json=None, transcript_json=None)

    with pytest.raises(Exception):
        _build_clip_summary(_get_clip_or_404("clip-2"))


def test_generate_then_regenerate_creates_two_versions(monkeypatch):
    init_db()
    _make_clip("clip-3", analysis_json=json.dumps({"suggested_title": "T", "reason": "R"}), transcript_json=None)

    responses = iter([_FAKE_RESPONSE_V1, _FAKE_RESPONSE_V2])
    monkeypatch.setattr("app.pipeline.social_kit.complete_chat", lambda *a, **k: next(responses))

    first = _generate_and_save("clip-3", "youtube_shorts", _PROVIDER)
    assert json.loads(first.titles_json)[0]["title"] == "Judul A"
    assert first.description == "Deskripsi versi 1"
    assert first.hashtags == "#tag1 #tag2"

    second = _generate_and_save("clip-3", "youtube_shorts", _PROVIDER)
    assert second.id == first.id  # same platform -> same row, updated in place
    assert second.description == "Deskripsi versi 2"

    with get_connection() as conn:
        versions = conn.execute(
            "SELECT version FROM social_kit_versions WHERE social_kit_id = ? ORDER BY version", (first.id,)
        ).fetchall()
    assert [v["version"] for v in versions] == [1, 2]


def test_generate_social_kit_parses_fenced_json_response(monkeypatch):
    fenced = f"```json\n{_FAKE_RESPONSE_V1}\n```"
    monkeypatch.setattr("app.pipeline.social_kit.complete_chat", lambda *a, **k: fenced)

    content = generate_social_kit(_PROVIDER, "some clip summary", "tiktok")

    assert len(content.titles) == 3
    assert content.titles[0].title == "Judul A"
    assert content.hashtags == ["#tag1", "tag2"]

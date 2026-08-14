from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from app.api.clips import (
    CaptureIntroFrameRequest,
    UpdateIntroFrameRequest,
    capture_intro_frame,
    get_intro_frame,
    update_intro_frame,
    upload_intro_frame,
)
from app.core.config import get_settings
from app.db.connection import get_connection, init_db


def _make_project_and_clip(project_id: str, clip_id: str, video_path: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
            "VALUES (?, 'p', 'v.mp4', 'queued', 'now', 'now')",
            (project_id,),
        )
        conn.execute(
            """
            INSERT INTO clips (id, project_id, start_time, end_time, duration, video_path, status, created_at, updated_at)
            VALUES (?, ?, 0, 5, 5, ?, 'completed', 'now', 'now')
            """,
            (clip_id, project_id, video_path),
        )
        conn.commit()


def test_get_intro_frame_defaults_when_none_saved():
    init_db()
    _make_project_and_clip("proj-1", "clip-1")

    response = get_intro_frame("clip-1")

    assert response.intro.enabled is False
    assert response.image_path is None


def test_get_intro_frame_404_for_missing_clip():
    init_db()
    with pytest.raises(HTTPException) as exc_info:
        get_intro_frame("does-not-exist")
    assert exc_info.value.status_code == 404


def test_update_intro_frame_persists_enabled_and_duration():
    init_db()
    _make_project_and_clip("proj-2", "clip-2")

    response = update_intro_frame("clip-2", UpdateIntroFrameRequest(enabled=True, duration_seconds=0.8))

    assert response.intro.enabled is True
    assert response.intro.duration_seconds == 0.8

    with get_connection() as conn:
        row = conn.execute("SELECT intro_json_path FROM clips WHERE id = ?", ("clip-2",)).fetchone()
    assert row["intro_json_path"] is not None

    # Round-trips through a fresh GET.
    reloaded = get_intro_frame("clip-2")
    assert reloaded.intro.enabled is True
    assert reloaded.intro.duration_seconds == 0.8


def test_capture_intro_frame_calls_extract_frame_and_saves_document(monkeypatch, tmp_path):
    init_db()
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video")
    _make_project_and_clip("proj-3", "clip-3", video_path=str(video_path))

    settings = get_settings()
    rendered_path = settings.clip_rendered_path("proj-3", "clip-3")
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_bytes(b"rendered master")

    captured = {}

    def fake_extract_frame(source_video, timestamp, output_path):
        captured["args"] = (source_video, timestamp, output_path)
        from pathlib import Path

        Path(output_path).write_bytes(b"fake frame")

    monkeypatch.setattr("app.api.clips.extract_frame", fake_extract_frame)

    response = capture_intro_frame("clip-3", CaptureIntroFrameRequest(timestamp=1.2, duration_seconds=0.8))

    assert captured["args"][0] == str(rendered_path)  # prefers rendered.mp4 over video_path
    assert captured["args"][1] == 1.2
    assert response.intro.enabled is True
    assert response.intro.source == "captured"
    assert response.intro.source_timestamp == 1.2
    assert response.intro.duration_seconds == 0.8
    assert response.image_path is not None


def test_capture_intro_frame_400s_when_clip_not_generated():
    init_db()
    _make_project_and_clip("proj-4", "clip-4", video_path=None)

    with pytest.raises(HTTPException) as exc_info:
        capture_intro_frame("clip-4", CaptureIntroFrameRequest(timestamp=0.0))
    assert exc_info.value.status_code == 400


def test_upload_intro_frame_rejects_unsupported_content_type():
    init_db()
    _make_project_and_clip("proj-5", "clip-5")
    upload = UploadFile(filename="x.gif", file=io.BytesIO(b"data"), headers={"content-type": "image/gif"})

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(upload_intro_frame("clip-5", duration_seconds=2.0, file=upload))
    assert exc_info.value.status_code == 400


def test_upload_intro_frame_converts_and_saves_document(monkeypatch):
    init_db()
    _make_project_and_clip("proj-6", "clip-6")

    captured = {}

    def fake_convert_image_to_png(input_path, output_path):
        captured["args"] = (input_path, output_path)
        from pathlib import Path

        Path(output_path).write_bytes(b"fake png")

    monkeypatch.setattr("app.api.clips.convert_image_to_png", fake_convert_image_to_png)

    upload = UploadFile(filename="x.jpg", file=io.BytesIO(b"jpeg bytes"), headers={"content-type": "image/jpeg"})
    response = asyncio.run(upload_intro_frame("clip-6", duration_seconds=1.5, file=upload))

    assert captured["args"][0].endswith(".jpg")
    assert response.intro.enabled is True
    assert response.intro.source == "uploaded"
    assert response.intro.source_timestamp is None
    assert response.intro.duration_seconds == 1.5
    assert response.image_path is not None

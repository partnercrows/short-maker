from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.projects import delete_all_projects, delete_project, list_projects
from app.core.config import get_settings
from app.core.ffmpeg_utils import VideoMetadata
from app.db.connection import get_connection, init_db


def _make_project(project_id: str, *, source_bytes: int = 1024, clip_bytes: int = 512) -> None:
    settings = get_settings()
    source_path = settings.project_source_path(project_id)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"0" * source_bytes)
    clip_path = settings.clip_dir(project_id, f"clip-{project_id}") / "video.mp4"
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    clip_path.write_bytes(b"0" * clip_bytes)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, source_duration, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 10.0, 'queued', 'now', 'now')",
            (project_id, project_id, str(source_path)),
        )
        conn.execute(
            "INSERT INTO clips (id, project_id, start_time, end_time, duration, status, created_at, updated_at) "
            "VALUES (?, ?, 0, 5, 5, 'completed', 'now', 'now')",
            (f"clip-{project_id}", project_id),
        )
        conn.execute(
            "INSERT INTO jobs (id, project_id, type, status, created_at) VALUES (?, ?, 'analyze_video', 'completed', 'now')",
            (f"job-{project_id}", project_id),
        )
        conn.commit()


def test_list_projects_reports_storage_used_on_disk():
    init_db()
    _make_project("proj-size", source_bytes=2048, clip_bytes=1024)

    project = list_projects()[0]

    assert project.storage_bytes == 3072


def test_delete_project_removes_its_files_and_cascaded_rows():
    init_db()
    _make_project("proj-del", source_bytes=2048, clip_bytes=1024)
    project_dir = get_settings().project_dir("proj-del")

    result = delete_project("proj-del")

    assert result.deleted_projects == 1
    assert result.freed_bytes == 3072
    assert result.failed_paths == []
    assert not project_dir.exists()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM clips").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 0


def test_delete_project_404s_for_an_unknown_id():
    init_db()

    with pytest.raises(HTTPException) as exc_info:
        delete_project("nope")
    assert exc_info.value.status_code == 404


def test_delete_project_still_removes_the_row_when_a_file_cannot_be_deleted(monkeypatch):
    init_db()
    _make_project("proj-locked")

    from app.api import projects as projects_api
    from app.core.project_storage import StorageDeletion

    monkeypatch.setattr(
        projects_api, "delete_directory", lambda path: StorageDeletion(freed_bytes=1024, failed_paths=["locked.mp4"])
    )

    result = delete_project("proj-locked")

    assert result.failed_paths == ["locked.mp4"]
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 0


def test_delete_all_projects_clears_every_project_and_its_storage():
    init_db()
    _make_project("proj-a", source_bytes=1024, clip_bytes=0)
    _make_project("proj-b", source_bytes=2048, clip_bytes=0)
    settings = get_settings()

    result = delete_all_projects()

    assert result.deleted_projects == 2
    assert result.freed_bytes == 3072
    assert not settings.project_dir("proj-a").exists()
    assert not settings.project_dir("proj-b").exists()
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 0


def test_delete_all_projects_on_an_empty_history_is_a_no_op():
    init_db()

    result = delete_all_projects()

    assert result.deleted_projects == 0
    assert result.freed_bytes == 0


def test_create_project_rejects_a_name_that_already_exists(tmp_path):
    """The duplicate that started this: a second click while the source video
    was still copying made a second project, and the Clips step then showed
    the empty one."""
    from app.api.projects import create_project
    from app.api.schemas import ProjectCreate

    init_db()
    source = tmp_path / "video.mp4"
    source.write_bytes(b"0" * 64)
    _make_project("proj-original")
    with get_connection() as conn:
        conn.execute("UPDATE projects SET name = 'Natasha' WHERE id = 'proj-original'")
        conn.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_project(ProjectCreate(name="natasha", source_video_path=str(source)))  # differs only in case

    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 1


def test_create_project_rejects_before_copying_the_source_video(tmp_path, monkeypatch):
    from app.api import projects as projects_api
    from app.api.schemas import ProjectCreate

    init_db()
    source = tmp_path / "video.mp4"
    source.write_bytes(b"0" * 64)
    _make_project("proj-taken")
    with get_connection() as conn:
        conn.execute("UPDATE projects SET name = 'Taken' WHERE id = 'proj-taken'")
        conn.commit()

    def _should_not_copy(*args, **kwargs):
        raise AssertionError("the source video must not be copied for a name that is already taken")

    monkeypatch.setattr(projects_api.shutil, "copyfile", _should_not_copy)

    with pytest.raises(HTTPException) as exc_info:
        projects_api.create_project(ProjectCreate(name="Taken", source_video_path=str(source)))
    assert exc_info.value.status_code == 409


def test_create_project_cleans_up_its_copy_when_the_insert_loses_a_race(tmp_path, monkeypatch):
    """Both requests passed the name check before either inserted; the unique
    index rejects the loser, whose copied video must not be left behind."""
    import sqlite3

    from app.api import projects as projects_api
    from app.api.schemas import ProjectCreate

    init_db()
    source = tmp_path / "video.mp4"
    source.write_bytes(b"0" * 64)
    monkeypatch.setattr(projects_api, "_raise_if_name_taken", lambda name: None)
    monkeypatch.setattr(
        projects_api, "probe_metadata", lambda path: VideoMetadata(duration=10.0, width=1920, height=1080, fps=30.0)
    )

    real_connection = projects_api.get_connection

    class _Conflicting:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, *args, **kwargs):
            raise sqlite3.IntegrityError("UNIQUE constraint failed: projects.name")

    monkeypatch.setattr(projects_api, "get_connection", lambda: _Conflicting())

    with pytest.raises(HTTPException) as exc_info:
        projects_api.create_project(ProjectCreate(name="Racer", source_video_path=str(source)))

    assert exc_info.value.status_code == 409
    monkeypatch.setattr(projects_api, "get_connection", real_connection)
    leftovers = [p for p in get_settings().projects_dir.iterdir() if p.is_dir()]
    assert leftovers == []

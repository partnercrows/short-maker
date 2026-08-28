from __future__ import annotations

import threading

import pytest

from app.core.ffmpeg_utils import VideoMetadata
from app.db.connection import get_connection, init_db
from app.jobs import runners
from app.jobs.manager import job_manager
from app.jobs.models import JobType


def _make_project_and_clip(project_id: str, clip_id: str, *, start: float, container_duration: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, source_duration, status, created_at, updated_at) "
            "VALUES (?, 'p', 'source.mp4', ?, 'queued', 'now', 'now')",
            (project_id, container_duration),
        )
        conn.execute(
            "INSERT INTO clips (id, project_id, start_time, end_time, duration, score, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 90, 'candidate', 'now', 'now')",
            (clip_id, project_id, start, start + 30.0, 30.0),
        )
        conn.commit()


def _truncated_source(monkeypatch, video_duration: float, container_duration: float) -> None:
    """A partially-downloaded source: audio to `container_duration`, picture
    only to `video_duration`."""
    monkeypatch.setattr(
        runners,
        "probe_metadata",
        lambda path: VideoMetadata(
            duration=container_duration, width=1920, height=1080, fps=30.0, video_duration=video_duration
        ),
    )


def test_generate_job_fails_legibly_when_clip_starts_past_last_video_frame(monkeypatch):
    init_db()
    _make_project_and_clip("proj-trunc", "clip-past-end", start=1537.5, container_duration=4204.5)
    _truncated_source(monkeypatch, video_duration=1450.9, container_duration=4204.5)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("cut_subclip must not run for a clip past the last video frame")

    monkeypatch.setattr(runners, "cut_subclip", _should_not_run)

    job = job_manager.create(JobType.GENERATE_CLIP, project_id="proj-trunc")
    runners.run_generate_job(job.id, "clip-past-end", include_subtitle=False)

    finished = job_manager.get(job.id)
    assert finished.status == "failed"
    assert "24:10" in finished.error  # where the picture actually stops
    assert "incomplete" in finished.error
    with get_connection() as conn:
        assert conn.execute("SELECT status FROM clips WHERE id = 'clip-past-end'").fetchone()["status"] == "failed"


def test_generate_job_proceeds_when_clip_is_inside_the_video_track(monkeypatch):
    init_db()
    _make_project_and_clip("proj-ok", "clip-inside", start=1281.1, container_duration=4204.5)
    _truncated_source(monkeypatch, video_duration=1450.9, container_duration=4204.5)

    cuts = []
    monkeypatch.setattr(runners, "cut_subclip", lambda *args: cuts.append(args))
    monkeypatch.setattr(runners, "resolve_reframe", lambda **kwargs: object())
    monkeypatch.setattr(runners, "render_clip", lambda *args: None)
    monkeypatch.setattr(runners.shutil, "copyfile", lambda *args: None)

    job = job_manager.create(JobType.GENERATE_CLIP, project_id="proj-ok")
    runners.run_generate_job(job.id, "clip-inside", include_subtitle=False)

    assert len(cuts) == 1
    assert job_manager.get(job.id).status == "completed"


def test_render_slot_queues_instead_of_running_every_clip_at_once():
    """Eight simultaneous ffmpeg encodes is what killed the cut with a bare
    AVERROR_EXTERNAL; extra clips must wait rather than pile on."""
    init_db()
    slots = threading.BoundedSemaphore(1)
    runners._RENDER_SLOTS, original = slots, runners._RENDER_SLOTS
    try:
        holder = job_manager.create(JobType.GENERATE_CLIP)
        waiter = job_manager.create(JobType.GENERATE_CLIP)
        entered = threading.Event()

        def second_render():
            with runners._render_slot(waiter.id):
                entered.set()

        with runners._render_slot(holder.id):
            thread = threading.Thread(target=second_render, daemon=True)
            thread.start()
            assert not entered.wait(timeout=1.5)  # still queued behind the first
            assert job_manager.get(waiter.id).current_step == "Waiting for another clip to finish rendering"

        assert entered.wait(timeout=5)  # slot released -> it runs
        thread.join(timeout=5)
    finally:
        runners._RENDER_SLOTS = original


def test_render_slot_honours_cancellation_while_queued():
    init_db()
    slots = threading.BoundedSemaphore(1)
    runners._RENDER_SLOTS, original = slots, runners._RENDER_SLOTS
    try:
        holder = job_manager.create(JobType.GENERATE_CLIP)
        waiter = job_manager.create(JobType.GENERATE_CLIP)
        job_manager.cancel(waiter.id)

        with runners._render_slot(holder.id):
            with pytest.raises(runners.JobCancelled):
                with runners._render_slot(waiter.id):
                    pass
    finally:
        runners._RENDER_SLOTS = original

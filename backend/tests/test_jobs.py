from app.db.connection import get_connection, init_db
from app.jobs.manager import JobManager
from app.jobs.models import JobStatus, JobType


def _make_project(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
            "VALUES (?, 'p', 'v.mp4', 'queued', 'now', 'now')",
            (project_id,),
        )
        conn.commit()


def test_job_lifecycle():
    init_db()
    _make_project("proj-1")
    manager = JobManager()
    job = manager.create(JobType.ANALYZE_VIDEO, project_id="proj-1")
    assert job.status == JobStatus.QUEUED
    assert job.progress == 0

    manager.start(job.id)
    manager.update_progress(job.id, 42, current_step="Transcribing")
    running = manager.get(job.id)
    assert running.status == JobStatus.RUNNING
    assert running.progress == 42
    assert running.current_step == "Transcribing"

    manager.complete(job.id)
    finished = manager.get(job.id)
    assert finished.status == JobStatus.COMPLETED
    assert finished.progress == 100
    assert finished.finished_at is not None


def test_job_cancellation_sets_flag_and_status():
    init_db()
    manager = JobManager()
    job = manager.create(JobType.GENERATE_CLIP)
    assert not manager.is_cancelled(job.id)

    manager.cancel(job.id)

    assert manager.is_cancelled(job.id)
    assert manager.get(job.id).status == JobStatus.CANCELLED


def test_list_filters_by_project():
    init_db()
    _make_project("proj-a")
    _make_project("proj-b")
    manager = JobManager()
    manager.create(JobType.ANALYZE_VIDEO, project_id="proj-a")
    manager.create(JobType.ANALYZE_VIDEO, project_id="proj-b")

    assert len(manager.list(project_id="proj-a")) == 1
    assert len(manager.list(project_id="proj-b")) == 1
    assert len(manager.list()) == 2

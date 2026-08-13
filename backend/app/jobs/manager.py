"""SQLite-persisted job tracking.

Unlike both audited reference apps (auto-clipper: in-memory threads only,
clipforge: a JSON file), job state here survives a sidecar restart so the
History feature (PRD S30-31, S37) has something durable to show. Actual
pipeline execution (transcription, rendering, ...) is wired in during the
MVP pass; this manager only owns state transitions and cooperative
cancellation flags for now.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.jobs.models import Job, JobStatus, JobType


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """Coordinates job rows in SQLite with in-memory cancellation flags.

    Cancellation flags are process-local by design: a job's cancel event
    must be checked from the same process that started its worker thread
    or subprocess, so nothing here needs to survive a restart.
    """

    def __init__(self) -> None:
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def create(self, job_type: JobType, project_id: str | None = None) -> Job:
        job_id = str(uuid.uuid4())
        now = _now()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, project_id, type, status, progress, current_step, error, created_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, 0, NULL, NULL, ?, NULL, NULL)
                """,
                (job_id, project_id, job_type.value, JobStatus.QUEUED.value, now),
            )
            conn.commit()
        with self._lock:
            self._cancel_events[job_id] = threading.Event()
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> Job | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def list(self, project_id: str | None = None) -> list[Job]:
        query = "SELECT * FROM jobs"
        params: tuple = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY created_at DESC"
        with get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_job(row) for row in rows]

    def start(self, job_id: str) -> None:
        self._update(job_id, status=JobStatus.RUNNING, started_at=_now())

    def update_progress(self, job_id: str, progress: float, current_step: str | None = None) -> None:
        self._update(job_id, progress=progress, current_step=current_step)

    def complete(self, job_id: str) -> None:
        self._update(job_id, status=JobStatus.COMPLETED, progress=100, finished_at=_now())

    def fail(self, job_id: str, error: str) -> None:
        self._update(job_id, status=JobStatus.FAILED, error=error, finished_at=_now())

    def cancel(self, job_id: str) -> None:
        with self._lock:
            event = self._cancel_events.setdefault(job_id, threading.Event())
        event.set()
        self._update(job_id, status=JobStatus.CANCELLED, finished_at=_now())

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(job_id)
        return event.is_set() if event else False

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: float | None = None,
        current_step: str | None = None,
        error: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[object] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status.value)
        if progress is not None:
            fields.append("progress = ?")
            values.append(progress)
        if current_step is not None:
            fields.append("current_step = ?")
            values.append(current_step)
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if started_at is not None:
            fields.append("started_at = ?")
            values.append(started_at)
        if finished_at is not None:
            fields.append("finished_at = ?")
            values.append(finished_at)
        if not fields:
            return
        values.append(job_id)
        with get_connection() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"],
        project_id=row["project_id"],
        type=JobType(row["type"]),
        status=JobStatus(row["status"]),
        progress=row["progress"],
        current_step=row["current_step"],
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


job_manager = JobManager()

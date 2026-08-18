from __future__ import annotations

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.core.config import get_settings
from app.db.connection import get_connection, init_db
from app.jobs import runners
from app.jobs.manager import job_manager
from app.jobs.models import JobType
from app.pipeline.ai_analysis.clip_selector import CandidateClip
from app.pipeline.transcribe import Segment, TranscriptResult, Word

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")
_FAKE_TRANSCRIPT = TranscriptResult(
    words=[Word(text="hello", start=0.0, end=0.5)],
    segments=[Segment(start=0.0, end=0.5, text="hello")],
    text="hello",
)
_FAKE_CANDIDATE = CandidateClip(
    start=0.0,
    end=5.0,
    score=90,
    hook_score=90,
    curiosity_score=90,
    emotion_score=90,
    information_score=90,
    reason="good",
    suggested_title="Title",
)


def _make_project(project_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, source_duration, status, created_at, updated_at) "
            "VALUES (?, 'p', 'v.mp4', 10.0, 'queued', 'now', 'now')",
            (project_id,),
        )
        conn.commit()


def test_run_analyze_job_transcribes_when_no_existing_transcript(monkeypatch):
    init_db()
    _make_project("proj-fresh")

    calls = {"extract_audio": 0, "transcribe": 0}
    monkeypatch.setattr(runners, "extract_audio", lambda *a, **k: calls.__setitem__("extract_audio", calls["extract_audio"] + 1))

    class _FakeTranscriber:
        def transcribe(self, audio_path, on_progress=None):
            calls["transcribe"] += 1
            return _FAKE_TRANSCRIPT

    monkeypatch.setattr(runners, "get_transcriber", lambda *a, **k: _FakeTranscriber())
    monkeypatch.setattr(runners, "select_clips", lambda *a, **k: [_FAKE_CANDIDATE])

    job = job_manager.create(JobType.ANALYZE_VIDEO, project_id="proj-fresh")
    runners.run_analyze_job(job.id, "proj-fresh", _PROVIDER, num_clips=None)

    finished = job_manager.get(job.id)
    assert finished.status == "completed"
    assert calls["extract_audio"] == 1
    assert calls["transcribe"] == 1

    transcript_path = get_settings().project_analysis_dir("proj-fresh") / "transcript.json"
    assert transcript_path.is_file()


def test_run_analyze_job_reuses_existing_transcript_without_retranscribing(monkeypatch):
    init_db()
    _make_project("proj-retry")

    # Simulate a prior attempt that already finished transcription.
    analysis_dir = get_settings().project_analysis_dir("proj-retry")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "transcript.json").write_text(_FAKE_TRANSCRIPT.model_dump_json(), encoding="utf-8")

    def _fail_if_called(*a, **k):
        raise AssertionError("should not re-extract audio when a transcript already exists")

    monkeypatch.setattr(runners, "extract_audio", _fail_if_called)
    monkeypatch.setattr(runners, "get_transcriber", _fail_if_called)

    captured_transcript = {}

    def fake_select_clips(provider, transcript, num_clips, video_duration):
        captured_transcript["transcript"] = transcript
        return [_FAKE_CANDIDATE]

    monkeypatch.setattr(runners, "select_clips", fake_select_clips)

    job = job_manager.create(JobType.ANALYZE_VIDEO, project_id="proj-retry")
    runners.run_analyze_job(job.id, "proj-retry", _PROVIDER, num_clips=None)

    finished = job_manager.get(job.id)
    assert finished.status == "completed"
    assert captured_transcript["transcript"].text == "hello"


def test_run_analyze_job_retry_after_ai_failure_reuses_transcript(monkeypatch):
    """The exact scenario reported: the AI provider step fails, the user
    clicks Analyze again -- the retry must not redo transcription."""
    init_db()
    _make_project("proj-retry-2")

    transcribe_calls = {"n": 0}
    monkeypatch.setattr(runners, "extract_audio", lambda *a, **k: None)

    class _FakeTranscriber:
        def transcribe(self, audio_path, on_progress=None):
            transcribe_calls["n"] += 1
            return _FAKE_TRANSCRIPT

    monkeypatch.setattr(runners, "get_transcriber", lambda *a, **k: _FakeTranscriber())

    def failing_select_clips(*a, **k):
        raise RuntimeError("503 UNAVAILABLE. high demand")

    monkeypatch.setattr(runners, "select_clips", failing_select_clips)

    job1 = job_manager.create(JobType.ANALYZE_VIDEO, project_id="proj-retry-2")
    runners.run_analyze_job(job1.id, "proj-retry-2", _PROVIDER, num_clips=None)
    assert job_manager.get(job1.id).status == "failed"
    assert transcribe_calls["n"] == 1

    # Retry: the AI provider is healthy again this time.
    monkeypatch.setattr(runners, "select_clips", lambda *a, **k: [_FAKE_CANDIDATE])
    job2 = job_manager.create(JobType.ANALYZE_VIDEO, project_id="proj-retry-2")
    runners.run_analyze_job(job2.id, "proj-retry-2", _PROVIDER, num_clips=None)

    assert job_manager.get(job2.id).status == "completed"
    assert transcribe_calls["n"] == 1  # still just the one transcription from job1

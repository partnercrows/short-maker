import time

from app.api.system import download_gpu_pack_endpoint, get_gpu_pack_status
from app.db.connection import init_db
from app.jobs.manager import job_manager
from app.jobs.models import JobType


def test_get_gpu_pack_status_reflects_installed_state(monkeypatch):
    monkeypatch.setattr("app.api.system.is_gpu_pack_installed", lambda: True)
    assert get_gpu_pack_status().installed is True

    monkeypatch.setattr("app.api.system.is_gpu_pack_installed", lambda: False)
    assert get_gpu_pack_status().installed is False


def test_download_gpu_pack_endpoint_creates_job_and_runs_it(monkeypatch):
    init_db()
    monkeypatch.setattr("app.jobs.runners.download_gpu_pack", lambda on_progress=None: None)
    monkeypatch.setattr("app.jobs.runners.ensure_cuda_dlls_on_path", lambda: None)
    monkeypatch.setattr("app.jobs.runners.probe_capabilities.cache_clear", lambda: None)

    job = download_gpu_pack_endpoint()
    assert job.type == JobType.DOWNLOAD_GPU_PACK
    assert job.status in ("queued", "running")

    for _ in range(50):
        current = job_manager.get(job.id)
        if current.status not in ("queued", "running"):
            break
        time.sleep(0.05)

    assert job_manager.get(job.id).status == "completed"

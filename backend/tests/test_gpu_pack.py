from __future__ import annotations

import io
import zipfile
from contextlib import contextmanager

from app.core import gpu_pack
from app.core.config import get_settings


def _make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nvidia/cublas/bin/cublas64_12.dll", b"fake cublas")
        zf.writestr("nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll", b"fake nvrtc")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data
        self.headers = {"content-length": str(len(data))}

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self, chunk_size: int):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i : i + chunk_size]


def test_is_gpu_pack_installed_false_when_missing():
    assert gpu_pack.is_gpu_pack_installed() is False


def test_is_gpu_pack_installed_true_when_marker_present():
    marker = get_settings().gpu_pack_dir / gpu_pack._MARKER_FILE
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"fake")

    assert gpu_pack.is_gpu_pack_installed() is True


def test_download_gpu_pack_extracts_files_and_reports_progress(monkeypatch):
    zip_bytes = _make_zip_bytes()

    @contextmanager
    def fake_stream(method, url, follow_redirects=True, timeout=None):
        yield _FakeResponse(zip_bytes)

    monkeypatch.setattr(gpu_pack.httpx, "stream", fake_stream)

    progress_values = []
    gpu_pack.download_gpu_pack(on_progress=progress_values.append)

    assert gpu_pack.is_gpu_pack_installed()
    assert progress_values
    assert progress_values[-1] == 1.0
    assert (get_settings().gpu_pack_dir / "nvidia" / "cuda_nvrtc" / "bin" / "nvrtc64_120_0.dll").read_bytes() == b"fake nvrtc"


def test_download_gpu_pack_raises_if_extraction_incomplete(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll", b"fake nvrtc")
    incomplete_zip = buf.getvalue()

    @contextmanager
    def fake_stream(method, url, follow_redirects=True, timeout=None):
        yield _FakeResponse(incomplete_zip)

    monkeypatch.setattr(gpu_pack.httpx, "stream", fake_stream)

    try:
        gpu_pack.download_gpu_pack()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass

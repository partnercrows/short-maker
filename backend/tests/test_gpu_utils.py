import os
import sys

from app.core import gpu_utils


def test_finds_cuda_dlls_relative_to_venv_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("PATH", "C:\\Windows")

    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    cublas_dir = tmp_path / ".venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin"
    cublas_dir.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable", str(venv_python))

    gpu_utils.ensure_cuda_dlls_on_path()

    assert str(cublas_dir) in os.environ["PATH"]


def test_finds_cuda_dlls_inside_frozen_meipass(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "short-maker-backend.exe"))

    cublas_dir = tmp_path / "nvidia" / "cublas" / "bin"
    cublas_dir.mkdir(parents=True)

    gpu_utils.ensure_cuda_dlls_on_path()

    assert str(cublas_dir) in os.environ["PATH"]


def test_finds_cuda_dlls_in_downloaded_gpu_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "nonexistent" / "python.exe"))

    cublas_dir = tmp_path / "gpu-pack" / "nvidia" / "cublas" / "bin"
    cublas_dir.mkdir(parents=True)

    gpu_utils.ensure_cuda_dlls_on_path()

    assert str(cublas_dir) in os.environ["PATH"]


def test_does_nothing_when_no_cuda_dlls_found(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "C:\\Windows")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / ".venv" / "Scripts" / "python.exe"))

    gpu_utils.ensure_cuda_dlls_on_path()

    assert os.environ["PATH"] == "C:\\Windows"

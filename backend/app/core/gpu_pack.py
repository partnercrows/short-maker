"""On-demand download of the optional NVIDIA CUDA runtime DLLs.

PRD S39 says not to make an NVIDIA GPU mandatory, and bundling cuBLAS/NVRTC
(~590MB compressed) into every install would be dead weight for the AMD/Intel/
no-GPU majority of machines. Instead the base installer stays small and a
user with an NVIDIA GPU downloads this once, on demand, when they turn on
"Use GPU" in Settings -- gpu_utils.ensure_cuda_dlls_on_path() then finds it
alongside the dev-venv and frozen-bundle locations it already checks.
"""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import httpx

from app.core.config import get_settings

GPU_PACK_URL = "https://github.com/partnercrows/short-maker/releases/download/gpu-pack-cuda12-v1/gpu-pack-cuda12.zip"

# Matches the "nvidia/<package>/bin" layout ensure_cuda_dlls_on_path() looks for.
_MARKER_FILE = Path("nvidia") / "cublas" / "bin" / "cublas64_12.dll"


def is_gpu_pack_installed() -> bool:
    return (get_settings().gpu_pack_dir / _MARKER_FILE).is_file()


def download_gpu_pack(on_progress: Callable[[float], None] | None = None) -> None:
    """Downloads and extracts the GPU pack. Raises on any failure -- the
    caller (a job runner) reports that through the job's error field, the
    same way every other pipeline stage does."""
    settings = get_settings()
    settings.gpu_pack_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    try:
        with httpx.stream("GET", GPU_PACK_URL, follow_redirects=True, timeout=120.0) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        on_progress(min(1.0, downloaded / total))

        with zipfile.ZipFile(tmp_path) as zf:
            zf.extractall(settings.gpu_pack_dir)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not is_gpu_pack_installed():
        raise RuntimeError("GPU pack downloaded but expected files are missing after extraction.")

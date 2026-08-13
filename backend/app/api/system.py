"""Device capability probing, so the Settings UI can show whether GPU
transcription is actually usable on this machine rather than just
offering a toggle that might silently fail.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import require_local_token

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require_local_token)])


class SystemCapabilities(BaseModel):
    gpu_name: str | None
    cuda_device_count: int
    gpu_transcription_ready: bool
    detail: str


def _gpu_name() -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        name = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return name
    except Exception:  # noqa: BLE001 -- no nvidia-smi (no NVIDIA GPU, or driver not installed) is a normal outcome
        return None


@lru_cache
def probe_capabilities() -> SystemCapabilities:
    gpu_name = _gpu_name()

    try:
        import ctranslate2

        cuda_device_count = ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001
        cuda_device_count = 0

    if cuda_device_count == 0:
        return SystemCapabilities(
            gpu_name=gpu_name, cuda_device_count=0, gpu_transcription_ready=False, detail="No CUDA-capable GPU detected."
        )

    try:
        from faster_whisper import WhisperModel

        WhisperModel("tiny", device="cuda", compute_type="float16")
        return SystemCapabilities(
            gpu_name=gpu_name,
            cuda_device_count=cuda_device_count,
            gpu_transcription_ready=True,
            detail="GPU transcription is ready.",
        )
    except Exception as exc:  # noqa: BLE001 -- e.g. missing cuBLAS/cuDNN runtime DLLs
        return SystemCapabilities(
            gpu_name=gpu_name,
            cuda_device_count=cuda_device_count,
            gpu_transcription_ready=False,
            detail=f"GPU detected but not usable yet: {exc}",
        )


@router.get("/capabilities", response_model=SystemCapabilities)
def get_capabilities() -> SystemCapabilities:
    return probe_capabilities()

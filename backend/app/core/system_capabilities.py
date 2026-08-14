"""Device capability probing, so the Settings UI can show whether GPU
transcription is actually usable on this machine rather than just
offering a toggle that might silently fail.

Lives in `core` (not `api`) so both the `/system/capabilities` route and
the GPU-pack download job can import `probe_capabilities` without the two
modules ending up importing each other.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache

from pydantic import BaseModel


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
        import numpy as np
        from faster_whisper import WhisperModel

        # Constructing the model alone doesn't touch cuBLAS -- ctranslate2
        # only loads it lazily on the first actual forward pass, so a build
        # missing cublas64_12.dll would still report "ready" here otherwise
        # and only fail later, mid real transcription. Force one real (if
        # trivial) computation with a second of silence so this check means
        # what it says.
        model = WhisperModel("tiny", device="cuda", compute_type="float16")
        silence = np.zeros(16000, dtype=np.float32)
        list(model.transcribe(silence)[0])

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

"""Makes the CUDA runtime DLLs from the pip-installed `nvidia-cublas-cu12`
package discoverable. Unlike PyTorch, ctranslate2 doesn't automatically
add these to the loader search path -- without this, `device="cuda"`
fails with "Library cublas64_12.dll is not found" even though the
package is installed, since Windows only searches PATH (or the
executable's own directory), not arbitrary site-packages folders.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.core.config import get_settings


def ensure_cuda_dlls_on_path() -> None:
    # Frozen (PyInstaller) builds don't have a real venv on disk -- `nvidia.*`
    # packages get collected into the onefile bundle's extraction dir
    # instead, so look there first. `sys.executable` in a frozen build is the
    # bundled exe itself, not a venv's python.exe, so the dev-mode
    # `parent.parent / "Lib" / "site-packages"` guess would silently find
    # nothing there. The on-demand GPU pack (app.core.gpu_pack) extracts to
    # yet another location -- the app's own data dir -- since the standalone
    # build doesn't bundle these DLLs at all (PRD S39/S47: keep them optional
    # rather than bloating every install by ~590MB for NVIDIA-only benefit).
    frozen_root = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else None
    site_packages = Path(sys.executable).parent.parent / "Lib" / "site-packages"
    gpu_pack_dir = get_settings().gpu_pack_dir

    roots = [r for r in (frozen_root, site_packages, gpu_pack_dir) if r is not None]
    candidate_dirs = [root / "nvidia" / pkg / "bin" for root in roots for pkg in ("cublas", "cuda_nvrtc", "cudnn")]
    existing = [str(d) for d in candidate_dirs if d.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing) + os.pathsep + os.environ.get("PATH", "")

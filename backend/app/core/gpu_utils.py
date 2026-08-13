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


def ensure_cuda_dlls_on_path() -> None:
    site_packages = Path(sys.executable).parent.parent / "Lib" / "site-packages"
    candidate_dirs = [
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cuda_nvrtc" / "bin",
        site_packages / "nvidia" / "cudnn" / "bin",
    ]
    existing = [str(d) for d in candidate_dirs if d.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join(existing) + os.pathsep + os.environ.get("PATH", "")

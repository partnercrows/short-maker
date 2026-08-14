"""Standalone entrypoint for the packaged (PyInstaller) backend -- Tauri
spawns this executable as a sidecar instead of the user running uvicorn by
hand. Kept separate from app/main.py so the dev workflow (`uvicorn
app.main:app --reload`) is unaffected.
"""

from __future__ import annotations

import uvicorn

from app.main import app

if __name__ == "__main__":
    # Pass the app object directly, not the "app.main:app" string form --
    # uvicorn's string-import path resolution doesn't work inside a frozen
    # PyInstaller bundle (there's no real package on disk to import by name).
    uvicorn.run(app, host="127.0.0.1", port=8000)

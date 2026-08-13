"""Local paths, ports and settings for the FastAPI sidecar.

Video processing must stay on the user's machine (PRD S4/S41), so every
path here resolves under a single per-OS app-data directory rather than
anything shared or uploaded.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def _default_app_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "ShortMaker"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ShortMaker"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "ShortMaker"


class Settings:
    def __init__(self) -> None:
        override = os.environ.get("SHORT_MAKER_DATA_DIR")
        self.data_dir = Path(override) if override else _default_app_data_dir()
        self.projects_dir = self.data_dir / "projects"
        self.temp_dir = self.data_dir / "temp"
        self.logs_dir = self.data_dir / "logs"
        self.db_path = self.data_dir / "short_maker.db"
        self.api_token_path = self.data_dir / ".api_token"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.projects_dir, self.temp_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.projects_dir / project_id

    def project_source_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "source" / "source.mp4"

    def project_analysis_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "analysis"

    def clip_dir(self, project_id: str, clip_id: str) -> Path:
        return self.project_dir(project_id) / "clips" / clip_id


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings

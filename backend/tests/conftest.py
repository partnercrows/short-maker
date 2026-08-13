from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test gets its own data dir instead of touching the real
    per-OS ShortMaker app-data directory."""
    from app.core import config

    monkeypatch.setenv("SHORT_MAKER_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()

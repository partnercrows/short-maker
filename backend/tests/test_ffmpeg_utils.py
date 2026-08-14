from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock

import pytest

from app.core import ffmpeg_utils


@pytest.fixture(autouse=True)
def _clear_binary_cache():
    ffmpeg_utils._find_binary.cache_clear()
    yield
    ffmpeg_utils._find_binary.cache_clear()


def test_find_binary_prefers_path(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    assert ffmpeg_utils._find_binary("ffmpeg") == "/usr/bin/ffmpeg"


def test_find_binary_falls_back_to_search_roots_when_not_on_path(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    fake_root = tmp_path / "packages"
    nested = fake_root / "SomePackage" / "bin"
    nested.mkdir(parents=True)
    fake_exe = nested / "ffprobe.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(ffmpeg_utils, "_FALLBACK_SEARCH_ROOTS", [fake_root])

    assert ffmpeg_utils._find_binary("ffprobe") == str(fake_exe)


def test_find_binary_raises_when_not_found_anywhere(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(ffmpeg_utils, "_FALLBACK_SEARCH_ROOTS", [tmp_path / "does-not-exist"])

    with pytest.raises(RuntimeError):
        ffmpeg_utils._find_binary("ffmpeg")


def test_extract_frame_builds_single_frame_command(tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "ffmpeg_path", lambda: "ffmpeg")
    captured = {}
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, check, capture_output: captured.setdefault("cmd", cmd) or MagicMock()
    )

    output_path = tmp_path / "frame.png"
    ffmpeg_utils.extract_frame("video.mp4", 3.5, str(output_path))

    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd and cmd[cmd.index("-ss") + 1] == "3.5"
    assert "-vframes" in cmd and cmd[cmd.index("-vframes") + 1] == "1"
    assert cmd[-1] == str(output_path)


def test_convert_image_to_png_builds_single_frame_command(tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg_utils, "ffmpeg_path", lambda: "ffmpeg")
    captured = {}
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, check, capture_output: captured.setdefault("cmd", cmd) or MagicMock()
    )

    output_path = tmp_path / "out.png"
    ffmpeg_utils.convert_image_to_png("input.jpg", str(output_path))

    cmd = captured["cmd"]
    assert "input.jpg" in cmd
    assert cmd[-1] == str(output_path)

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.youtube import DownloadRequest, VideoInfoRequest, download_video, get_video_info
from app.core.youtube_download import VideoInfo
from app.db.connection import init_db


def test_get_video_info_returns_parsed_info(monkeypatch):
    fake_info = VideoInfo(title="Some Video", duration=10.0, thumbnail_url="https://x/y.jpg", available_resolutions=[1080, 720])
    monkeypatch.setattr("app.api.youtube.fetch_video_info", lambda url: fake_info)

    result = get_video_info(VideoInfoRequest(url="https://youtube.com/watch?v=abc"))

    assert result.title == "Some Video"
    assert result.available_resolutions == [1080, 720]


def test_get_video_info_surfaces_errors_as_400(monkeypatch):
    def boom(url):
        raise ValueError("Video unavailable")

    monkeypatch.setattr("app.api.youtube.fetch_video_info", boom)

    with pytest.raises(HTTPException) as exc_info:
        get_video_info(VideoInfoRequest(url="https://youtube.com/watch?v=bad"))
    assert exc_info.value.status_code == 400
    assert "Video unavailable" in exc_info.value.detail


def test_download_video_requires_resolution_for_video_format():
    with pytest.raises(HTTPException) as exc_info:
        download_video(DownloadRequest(url="https://youtube.com/watch?v=abc", format="video", output_folder="C:/tmp"))
    assert exc_info.value.status_code == 400


def test_download_video_does_not_require_resolution_for_audio_format(monkeypatch):
    init_db()
    # Prevent the background thread from actually running a real download.
    monkeypatch.setattr("app.api.youtube.threading.Thread.start", lambda self: None)

    job = download_video(DownloadRequest(url="https://youtube.com/watch?v=abc", format="audio", output_folder="C:/tmp"))

    assert job.status == "queued"

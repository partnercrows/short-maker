from __future__ import annotations

from pathlib import Path

from app.core import youtube_download


class _FakeYDL:
    captured_opts: dict | None = None
    fake_info: dict = {}
    fake_prepared_filename: str = ""

    def __init__(self, opts):
        _FakeYDL.captured_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return _FakeYDL.fake_info

    def prepare_filename(self, info):
        return _FakeYDL.fake_prepared_filename


def test_fetch_video_info_dedupes_and_sorts_resolutions(monkeypatch):
    _FakeYDL.fake_info = {
        "title": "My Video",
        "duration": 123.4,
        "thumbnail": "https://example.com/thumb.jpg",
        "formats": [
            {"height": 1080, "vcodec": "avc1", "acodec": "none"},
            {"height": 720, "vcodec": "avc1", "acodec": "none"},
            {"height": 720, "vcodec": "vp9", "acodec": "none"},  # duplicate height, different codec
            {"height": 480, "vcodec": "avc1", "acodec": "none"},
            {"height": None, "vcodec": "none", "acodec": "mp4a"},  # audio-only, no height -- ignored
            {"height": 360, "vcodec": "none", "acodec": "mp4a"},  # audio-only but has height -- must be excluded (vcodec none)
        ],
    }
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))

    info = youtube_download.fetch_video_info("https://youtube.com/watch?v=abc")

    assert info.title == "My Video"
    assert info.duration == 123.4
    assert info.thumbnail_url == "https://example.com/thumb.jpg"
    assert info.available_resolutions == [1080, 720, 480]


def test_fetch_video_info_falls_back_to_url_when_title_missing(monkeypatch):
    _FakeYDL.fake_info = {"formats": []}
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))

    info = youtube_download.fetch_video_info("https://youtube.com/watch?v=xyz")

    assert info.title == "https://youtube.com/watch?v=xyz"
    assert info.available_resolutions == []


def test_download_youtube_video_builds_format_selector_and_merge_options(monkeypatch, tmp_path):
    _FakeYDL.fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "video.mp4")}]}
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    result = youtube_download.download_youtube_video("https://youtube.com/watch?v=abc", 720, str(tmp_path))

    assert result == tmp_path / "video.mp4"
    opts = _FakeYDL.captured_opts
    assert opts["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert opts["merge_output_format"] == "mp4"
    assert opts["ffmpeg_location"] == "ffmpeg"
    assert opts["noplaylist"] is True


def test_download_youtube_video_falls_back_when_no_requested_downloads(monkeypatch, tmp_path):
    _FakeYDL.fake_info = {}
    _FakeYDL.fake_prepared_filename = str(tmp_path / "video.webm")
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    result = youtube_download.download_youtube_video("https://youtube.com/watch?v=abc", 1080, str(tmp_path))

    assert result == tmp_path / "video.mp4"  # extension forced to the merge output format


def test_download_youtube_video_creates_output_folder(monkeypatch, tmp_path):
    dest = tmp_path / "nested" / "downloads"
    _FakeYDL.fake_info = {"requested_downloads": [{"filepath": str(dest / "video.mp4")}]}
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    youtube_download.download_youtube_video("https://youtube.com/watch?v=abc", 480, str(dest))

    assert dest.is_dir()


def test_download_youtube_audio_builds_mp3_extraction_options(monkeypatch, tmp_path):
    _FakeYDL.fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "song.mp3")}]}
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    result = youtube_download.download_youtube_audio("https://youtube.com/watch?v=abc", str(tmp_path))

    assert result == tmp_path / "song.mp3"
    opts = _FakeYDL.captured_opts
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    assert opts["ffmpeg_location"] == "ffmpeg"


def test_download_youtube_audio_falls_back_when_no_requested_downloads(monkeypatch, tmp_path):
    _FakeYDL.fake_info = {}
    _FakeYDL.fake_prepared_filename = str(tmp_path / "song.webm")
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    result = youtube_download.download_youtube_audio("https://youtube.com/watch?v=abc", str(tmp_path))

    assert result == tmp_path / "song.mp3"


def test_download_youtube_video_progress_hook_reports_fraction(monkeypatch, tmp_path):
    _FakeYDL.fake_info = {"requested_downloads": [{"filepath": str(tmp_path / "video.mp4")}]}
    monkeypatch.setattr(youtube_download, "yt_dlp", type("M", (), {"YoutubeDL": _FakeYDL}))
    monkeypatch.setattr(youtube_download, "ffmpeg_path", lambda: "ffmpeg")

    events = []
    youtube_download.download_youtube_video(
        "https://youtube.com/watch?v=abc", 720, str(tmp_path), on_progress=lambda frac, step: events.append((frac, step))
    )

    # The fake YoutubeDL never actually downloads, so simulate what yt-dlp
    # would call mid-download by invoking the captured hook directly.
    hook = _FakeYDL.captured_opts["progress_hooks"][0]
    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200})
    hook({"status": "finished"})

    assert events == [(0.25, "Downloading video"), (1.0, "Merging video and audio")]

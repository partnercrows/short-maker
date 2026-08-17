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


class _FakeDownloadError(Exception):
    pass


class _FakeYDLUtils:
    DownloadError = _FakeDownloadError


class _FakeYDLBotCheckThenRecover:
    """First call raises YouTube's bot-check error; any retry (with cookies) succeeds."""

    calls: list[dict] = []

    def __init__(self, opts):
        type(self).calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        if len(type(self).calls) == 1:
            raise _FakeDownloadError("Sign in to confirm you’re not a bot")
        return {"title": "Recovered Video", "formats": []}

    def prepare_filename(self, info):
        return "recovered.mp4"


class _FakeYDLAlwaysBotCheck:
    calls: list[dict] = []

    def __init__(self, opts):
        type(self).calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        raise _FakeDownloadError("Sign in to confirm you’re not a bot")


class _FakeYDLUnrelatedError:
    calls: list[dict] = []

    def __init__(self, opts):
        type(self).calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        raise _FakeDownloadError("Video unavailable")


def _fake_yt_dlp_module(ydl_class):
    return type("M", (), {"YoutubeDL": ydl_class, "utils": _FakeYDLUtils})


def test_fetch_video_info_recovers_via_browser_cookies_after_bot_check(monkeypatch):
    _FakeYDLBotCheckThenRecover.calls = []
    monkeypatch.setattr(youtube_download, "yt_dlp", _fake_yt_dlp_module(_FakeYDLBotCheckThenRecover))

    info = youtube_download.fetch_video_info("https://youtube.com/watch?v=abc")

    assert info.title == "Recovered Video"
    calls = _FakeYDLBotCheckThenRecover.calls
    assert len(calls) == 2
    assert "cookiesfrombrowser" not in calls[0]
    assert calls[1]["cookiesfrombrowser"] == (youtube_download._COOKIE_BROWSER_FALLBACKS[0],)


def test_fetch_video_info_raises_actionable_error_when_all_fallbacks_fail(monkeypatch):
    _FakeYDLAlwaysBotCheck.calls = []
    monkeypatch.setattr(youtube_download, "yt_dlp", _fake_yt_dlp_module(_FakeYDLAlwaysBotCheck))

    try:
        youtube_download.fetch_video_info("https://youtube.com/watch?v=abc")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "verify you're not a bot" in str(e)

    # one initial attempt + one per candidate browser
    assert len(_FakeYDLAlwaysBotCheck.calls) == 1 + len(youtube_download._COOKIE_BROWSER_FALLBACKS)


def test_fetch_video_info_does_not_retry_on_unrelated_errors(monkeypatch):
    _FakeYDLUnrelatedError.calls = []
    monkeypatch.setattr(youtube_download, "yt_dlp", _fake_yt_dlp_module(_FakeYDLUnrelatedError))

    try:
        youtube_download.fetch_video_info("https://youtube.com/watch?v=abc")
        assert False, "expected _FakeDownloadError"
    except _FakeDownloadError:
        pass

    assert len(_FakeYDLUnrelatedError.calls) == 1  # no retries attempted


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

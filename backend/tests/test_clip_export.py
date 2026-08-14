import json
import subprocess
from unittest.mock import MagicMock

from app.core import clip_export
from app.core.clip_export import (
    clip_base_name,
    composite_intro_and_video,
    copy_clip_to_folder,
    export_clip_to_folder,
    safe_filename,
)
from app.core.ffmpeg_utils import VideoMetadata
from app.pipeline.intro import IntroFrame


def test_safe_filename_replaces_unsafe_characters():
    assert safe_filename('Anak "Gifted": IQ Test?!') == "Anak _Gifted__ IQ Test__"


def test_safe_filename_falls_back_when_empty():
    assert safe_filename("   ") == "clip"


def test_clip_base_name_prefers_suggested_title():
    clip = {"id": "clip-1", "analysis_json": json.dumps({"suggested_title": "Judul Keren"})}
    assert clip_base_name(clip) == "Judul Keren"


def test_clip_base_name_falls_back_to_id_when_no_analysis():
    clip = {"id": "clip-2", "analysis_json": None}
    assert clip_base_name(clip) == "clip-2"


def test_copy_clip_to_folder_copies_video_and_subtitle(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video")
    subtitle = tmp_path / "sub.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")

    destination = tmp_path / "out"
    clip = {"id": "clip-3", "analysis_json": json.dumps({"suggested_title": "My Clip"})}

    result_path = copy_clip_to_folder(clip, video, str(subtitle), str(destination))

    assert result_path == destination / "My Clip.mp4"
    assert result_path.read_bytes() == b"fake video"
    assert (destination / "My Clip.srt").exists()


def test_composite_intro_and_video_builds_concat_filter_with_silent_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(clip_export, "probe_metadata", lambda path: VideoMetadata(duration=10, width=720, height=1280, fps=30))
    captured_cmd = {}

    def fake_run(cmd, check, capture_output):
        captured_cmd["cmd"] = cmd
        return MagicMock()

    monkeypatch.setattr(subprocess, "run", fake_run)

    output_path = tmp_path / "out.mp4"
    composite_intro_and_video("intro.png", "video.mp4", 0.8, str(output_path))

    cmd = captured_cmd["cmd"]
    assert "-loop" in cmd and "1" in cmd
    assert "0.8" in cmd  # duration passed both to -t and the anullsrc filter
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "anullsrc" in filter_complex
    assert "concat=n=2:v=1:a=1" in filter_complex
    assert "720" in filter_complex and "1280" in filter_complex


def test_export_clip_to_folder_falls_back_to_plain_copy_when_intro_disabled(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video")
    destination = tmp_path / "out"
    clip = {"id": "clip-1", "analysis_json": None}

    result = export_clip_to_folder(clip, video, None, str(destination), intro=IntroFrame(enabled=False, created_at="now"))

    assert result.read_bytes() == b"fake video"


def test_export_clip_to_folder_falls_back_to_plain_copy_when_intro_image_missing(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video")
    destination = tmp_path / "out"
    clip = {"id": "clip-1", "analysis_json": None}
    intro = IntroFrame(enabled=True, created_at="now")

    result = export_clip_to_folder(
        clip, video, None, str(destination), intro=intro, intro_image_path=tmp_path / "does-not-exist.png"
    )

    assert result.read_bytes() == b"fake video"


def test_export_clip_to_folder_composites_when_intro_enabled_and_image_present(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake video")
    image = tmp_path / "intro.png"
    image.write_bytes(b"fake image")
    destination = tmp_path / "out"
    clip = {"id": "clip-1", "analysis_json": None}
    intro = IntroFrame(enabled=True, duration_seconds=1.5, created_at="now")

    calls = {}

    def fake_composite(image_path, video_path, duration_seconds, output_path):
        calls["args"] = (image_path, video_path, duration_seconds)
        output_path.write_bytes(b"composited")

    monkeypatch.setattr(clip_export, "composite_intro_and_video", fake_composite)

    result = export_clip_to_folder(clip, video, None, str(destination), intro=intro, intro_image_path=image)

    assert result.read_bytes() == b"composited"
    assert calls["args"] == (image, video, 1.5)

import json

from app.core.clip_export import clip_base_name, copy_clip_to_folder, safe_filename


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

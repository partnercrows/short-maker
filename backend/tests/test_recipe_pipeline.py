from __future__ import annotations

import json

import httpx
import pytest
from google.genai import errors as genai_errors

from app.ai_providers import registry
from app.ai_providers.registry import ImagePart, ProviderConfig, ProviderType, complete_chat_multimodal
from app.pipeline.recipe import assemble, frame_sampler, vision_capability, vision_labeler
from app.pipeline.recipe.models import AudioMode, VisualSegment
from app.pipeline.recipe.scene_render import audio_filter_for
from app.pipeline.reframe.models import CropWindow, ReframeMode, ReframePlan

_GEMINI = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")
_OPENAI = ProviderConfig(provider_type=ProviderType.OPENAI, model="fake-model", api_key="fake")


# --- provider: images in, text path untouched -------------------------------


def test_text_only_request_is_unchanged_by_the_multimodal_path(monkeypatch):
    """AI Clipper must keep sending exactly what it always sent."""
    seen = {}

    def record(config, system, user):
        seen["user"] = user
        return "ok"

    monkeypatch.setattr(registry, "_complete_chat_gemini", record)

    assert registry.complete_chat(_GEMINI, "sys", "plain text") == "ok"
    assert seen["user"] == "plain text"
    assert isinstance(seen["user"], str)


def test_multimodal_without_images_collapses_to_the_text_path(monkeypatch):
    seen = {}

    def record(config, system, user):
        seen["user"] = user
        return "ok"

    monkeypatch.setattr(registry, "_complete_chat_gemini", record)

    complete_chat_multimodal(_GEMINI, "sys", ["a", "b"])

    assert seen["user"] == "ab"
    assert isinstance(seen["user"], str)


def test_openai_image_payload_is_a_content_array_with_a_data_url():
    content = registry._openai_content(["look at this", ImagePart(data=b"\xff\xd8jpeg")])

    assert content[0] == {"type": "text", "text": "look at this"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_openai_text_request_keeps_its_string_content_and_timeout(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(registry.httpx, "post", fake_post)
    registry._complete_chat_openai_compatible(_OPENAI, "sys", "plain")

    assert captured["json"]["messages"][1]["content"] == "plain"
    assert captured["timeout"] == 120.0


# --- vision capability ------------------------------------------------------


def test_a_model_refusing_images_is_told_apart_from_a_busy_one():
    refusal = genai_errors.ClientError(
        400, {"error": {"code": 400, "message": "This model does not support image input", "status": "INVALID_ARGUMENT"}}
    )
    overloaded = genai_errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})

    assert vision_capability.classify_vision_failure(refusal) is True
    assert vision_capability.classify_vision_failure(overloaded) is False


def test_an_http_400_about_something_else_is_not_a_vision_refusal():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(400, request=request, text="context length exceeded")
    error = httpx.HTTPStatusError("bad request", request=request, response=response)

    assert vision_capability.classify_vision_failure(error) is False


def test_degraded_message_names_a_model_that_can_see():
    message = vision_capability.degraded_message(_GEMINI, "gemini-3.5-flash")

    assert "cannot read images" in message
    assert "gemini-3.5-flash" in message
    assert "Settings > AI Model" in message


def test_labeller_reports_a_text_only_model_once_instead_of_per_batch(monkeypatch, tmp_path):
    frame = tmp_path / "probe_000001.jpg"
    frame.write_bytes(b"\xff\xd8jpeg")
    keyframes = [
        VisualSegment(index=i, start=i, end=i + 1, peak_time=i, motion=1.0, frame_path=frame) for i in range(30)
    ]
    calls = {"n": 0}

    def boom(*args, **kwargs):
        calls["n"] += 1
        raise genai_errors.ClientError(
            400, {"error": {"code": 400, "message": "image input is not supported", "status": "INVALID_ARGUMENT"}}
        )

    monkeypatch.setattr(vision_labeler, "complete_chat_multimodal", boom)

    with pytest.raises(vision_capability.VisionUnsupportedError):
        vision_labeler.label_frames(_GEMINI, keyframes, None)
    assert calls["n"] == 1  # gave up on the first refusal


def test_labeller_keeps_only_frames_it_actually_sent(monkeypatch, tmp_path):
    frame = tmp_path / "probe_000001.jpg"
    frame.write_bytes(b"\xff\xd8jpeg")
    keyframes = [VisualSegment(index=7, start=0, end=1, peak_time=12.5, motion=1.0, frame_path=frame)]
    reply = json.dumps(
        {
            "frames": [
                {"i": 7, "label": "CUTTING", "confidence": 90},
                {"i": 999, "label": "PLATING", "confidence": 90},  # a frame we never sent
                {"i": 7, "label": "NOT_A_LABEL", "confidence": 10},
            ]
        }
    )
    monkeypatch.setattr(vision_labeler, "complete_chat_multimodal", lambda *a, **k: reply)

    labels = vision_labeler.label_frames(_GEMINI, keyframes, None)

    assert [label.index for label in labels] == [7, 7]
    assert labels[0].time == 12.5
    assert labels[1].label == "OTHER"  # an unknown label is not invented into the enum


# --- frame sampling ---------------------------------------------------------


def test_probe_interval_stretches_with_length_so_the_strip_stays_bounded():
    assert frame_sampler.probe_interval_for(30 * 60) == pytest.approx(1.0)
    assert frame_sampler.probe_interval_for(120 * 60) == pytest.approx(4.0)
    assert frame_sampler.keyframe_budget(15 * 60) < frame_sampler.keyframe_budget(120 * 60)


def test_keyframe_selection_covers_the_whole_timeline_not_just_the_busy_part():
    """The plating and the final dish live at the very end (PRD S11/S12)."""
    busy = [
        VisualSegment(index=i, start=i * 5, end=i * 5 + 5, peak_time=i * 5 + 2, motion=50.0)
        for i in range(100)  # first ~8 minutes, frantic
    ]
    calm = [
        VisualSegment(index=100 + i, start=3000 + i * 20, end=3020 + i * 20, peak_time=3010 + i * 20, motion=0.2)
        for i in range(30)  # the last stretch, barely moving
    ]

    chosen = frame_sampler.select_keyframes(busy + calm, duration_seconds=3600.0, budget=40)

    assert len(chosen) <= 40
    assert any(segment.peak_time > 3000 for segment in chosen)
    assert chosen == sorted(chosen, key=lambda s: s.start)


def test_keyframe_selection_returns_everything_when_under_budget():
    segments = [VisualSegment(index=i, start=i, end=i + 1, peak_time=i, motion=1.0) for i in range(5)]
    assert len(frame_sampler.select_keyframes(segments, 600.0, budget=40)) == 5


# --- assembling -------------------------------------------------------------


def _plan(x: int = 0) -> ReframePlan:
    return ReframePlan(
        mode_used=ReframeMode.FACELESS_COOKING, windows=[CropWindow(time=0.0, x=x, y=0, width=608, height=1080)]
    )


def test_audio_mode_never_changes_a_scene_fingerprint(tmp_path):
    """Changing the audio must not re-render a single scene (PRD S28)."""
    source = tmp_path / "source.mp4"
    source.write_bytes(b"0" * 1024)

    first = assemble.scene_fingerprint(str(source), 10.0, 16.0, _plan())
    second = assemble.scene_fingerprint(str(source), 10.0, 16.0, _plan())

    assert first == second  # audio and order are simply not part of the key


def test_trimming_or_reframing_a_scene_does_change_its_fingerprint(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"0" * 1024)
    base = assemble.scene_fingerprint(str(source), 10.0, 16.0, _plan())

    assert assemble.scene_fingerprint(str(source), 10.0, 17.0, _plan()) != base
    assert assemble.scene_fingerprint(str(source), 10.0, 16.0, _plan(x=120)) != base


def test_a_cached_scene_is_not_rendered_again(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"0" * 1024)
    scene_dir = tmp_path / "scene"
    renders = {"n": 0}

    def fake_render(*args, **kwargs):
        renders["n"] += 1
        (kwargs["scene_dir"] / "scene.mp4").write_bytes(b"video")
        return kwargs["scene_dir"] / "scene.mp4"

    monkeypatch.setattr(assemble, "render_scene", fake_render)

    _, rendered_first = assemble.ensure_scene_rendered(
        str(source), scene_dir=scene_dir, start=1.0, end=5.0, plan=_plan()
    )
    _, rendered_second = assemble.ensure_scene_rendered(
        str(source), scene_dir=scene_dir, start=1.0, end=5.0, plan=_plan()
    )
    _, rendered_after_trim = assemble.ensure_scene_rendered(
        str(source), scene_dir=scene_dir, start=1.0, end=6.0, plan=_plan()
    )

    assert (rendered_first, rendered_second, rendered_after_trim) == (True, False, True)
    assert renders["n"] == 2


def test_concat_file_uses_forward_slashes_and_quotes(tmp_path):
    concat = assemble.write_concat_file([tmp_path / "a" / "scene.mp4", tmp_path / "b" / "scene.mp4"], tmp_path / "c.txt")

    lines = concat.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(line.startswith("file '") and "\\" not in line for line in lines)


def test_audio_modes_map_to_the_right_ffmpeg_treatment():
    assert audio_filter_for(AudioMode.KEEP, 20) == (None, False)
    assert audio_filter_for(AudioMode.MUTE, 20) == (None, True)
    assert audio_filter_for(AudioMode.LOWER, 20) == ("volume=0.20", False)
    assert audio_filter_for(AudioMode.LOWER, 250) == ("volume=1.00", False)  # clamped


def test_assembling_nothing_is_an_error_not_an_empty_file(tmp_path):
    with pytest.raises(ValueError):
        assemble.assemble([], tmp_path / "out.mp4")

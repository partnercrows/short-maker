import json

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.pipeline.ai_analysis import clip_selector
from app.pipeline.transcribe import Segment, TranscriptResult

_CONFIG = ProviderConfig(provider_type=ProviderType.GEMINI, model="gemini-2.0-flash", api_key="fake")
_TRANSCRIPT = TranscriptResult(
    words=[],
    segments=[
        Segment(start=0.0, end=5.0, text="Hello everyone, welcome back."),
        Segment(start=5.0, end=40.0, text="Today we're going to talk about something surprising."),
        Segment(start=40.0, end=100.0, text="And that's the whole story."),
    ],
    text="Hello everyone, welcome back. Today we're going to talk about something surprising. And that's the whole story.",
)


def test_build_prompt_includes_all_segments():
    system_prompt, user_prompt = clip_selector.build_prompt(_TRANSCRIPT, num_clips=3)
    assert "3 candidate clips" in system_prompt
    for segment in _TRANSCRIPT.segments:
        assert segment.text in user_prompt


def test_build_prompt_auto_mode_lets_the_model_decide_count():
    system_prompt, _ = clip_selector.build_prompt(_TRANSCRIPT, num_clips=None)
    assert "Decide the number of candidate clips yourself" in system_prompt
    assert "Return exactly" not in system_prompt


def _valid_response() -> str:
    return json.dumps(
        {
            "clips": [
                {
                    "start": 5.0,
                    "end": 40.0,
                    "score": 90,
                    "hook_score": 92,
                    "curiosity_score": 88,
                    "emotion_score": 80,
                    "information_score": 85,
                    "reason": "Strong hook.",
                    "suggested_title": "You Won't Believe This",
                }
            ]
        }
    )


def test_select_clips_parses_valid_response(monkeypatch):
    monkeypatch.setattr(clip_selector, "complete_chat", lambda *a, **k: _valid_response())
    clips = clip_selector.select_clips(_CONFIG, _TRANSCRIPT, num_clips=1)
    assert len(clips) == 1
    assert clips[0].suggested_title == "You Won't Believe This"


def test_select_clips_drops_too_short_clip(monkeypatch):
    response = json.dumps({"clips": [{"start": 0.0, "end": 2.0, "score": 90, "hook_score": 90, "curiosity_score": 90,
                                       "emotion_score": 90, "information_score": 90, "reason": "x", "suggested_title": "y"}]})
    monkeypatch.setattr(clip_selector, "complete_chat", lambda *a, **k: response)
    clips = clip_selector.select_clips(_CONFIG, _TRANSCRIPT, num_clips=1)
    assert clips == []


def test_select_clips_drops_clip_beyond_video_duration(monkeypatch):
    monkeypatch.setattr(clip_selector, "complete_chat", lambda *a, **k: _valid_response())
    clips = clip_selector.select_clips(_CONFIG, _TRANSCRIPT, num_clips=1, video_duration=10.0)
    assert clips == []


def test_select_clips_handles_response_wrapped_in_code_fence(monkeypatch):
    fenced = f"```json\n{_valid_response()}\n```"
    monkeypatch.setattr(clip_selector, "complete_chat", lambda *a, **k: fenced)
    clips = clip_selector.select_clips(_CONFIG, _TRANSCRIPT, num_clips=1)
    assert len(clips) == 1

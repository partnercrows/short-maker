from __future__ import annotations

import json

import pytest

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.pipeline.recipe import recipe_analyzer
from app.pipeline.recipe.models import FrameLabel, RecipeAnalysis, RecipeScene, TargetDuration, VisualSegment
from app.pipeline.transcribe import Segment, TranscriptResult

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")


def _transcript(text: str = "kita tumis bumbu dan masukkan ayam") -> TranscriptResult:
    return TranscriptResult(words=[], segments=[Segment(start=0.0, end=4.0, text=text)], text=text)


def _labels() -> list[FrameLabel]:
    return [
        FrameLabel(index=1, time=200.0, label="CUTTING", confidence=90, subject="chicken on a board"),
        FrameLabel(index=2, time=900.0, label="SAUTEING", confidence=85, subject="garlic in a wok"),
        FrameLabel(index=3, time=1800.0, label="PLATING", confidence=80, subject="plated chicken"),
        FrameLabel(index=4, time=3400.0, label="FINAL_DISH", confidence=95, subject="finished dish"),
    ]


def _response(scenes: list[dict], ingredients: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "recipe_name": "Ayam Kecap",
            "main_ingredient": "Ayam",
            "ingredients": ingredients if ingredients is not None else [{"name": "ayam", "confidence": 95}],
            "cooking_flow": ["Preparation", "Sauteing", "Plating"],
            "scenes": scenes,
        }
    )


def _scene(label: str, start: float, end: float, **extra) -> dict:
    scene = {
        "label": label,
        "title": label.title(),
        "start": start,
        "end": end,
        "is_hook": False,
        "vo_guide": f"{label} guide",
        "on_screen_text": label.lower(),
        "reason": "matters",
    }
    scene.update(extra)
    return scene


def _analyze(
    monkeypatch,
    raw: str,
    video_duration: float = 3600.0,
    target=TargetDuration.ONE_MINUTE,
    labels: list[FrameLabel] | None = None,
) -> RecipeAnalysis:
    """`labels=[]` opts out of gap-filling, for tests about something else."""
    monkeypatch.setattr(recipe_analyzer, "complete_chat", lambda *a, **k: raw)
    return recipe_analyzer.analyze_recipe(
        _PROVIDER,
        _labels() if labels is None else labels,
        _transcript(),
        target,
        [],
        video_duration=video_duration,
    )


def test_scenes_are_forced_into_chronological_order(monkeypatch):
    """A shuffled highlight reel is fine; a shuffled cooking video is not (PRD S11)."""
    raw = _response([_scene("PLATING", 1800, 1806), _scene("CUTTING", 200, 206), _scene("SAUTEING", 900, 908)])

    analysis = _analyze(monkeypatch, raw, labels=[])

    assert [scene.label for scene in analysis.scenes] == ["CUTTING", "SAUTEING", "PLATING"]
    assert [scene.order for scene in analysis.scenes] == [0, 1, 2]


def test_final_dish_hook_may_open_out_of_order(monkeypatch):
    raw = _response(
        [_scene("FINAL_DISH", 3400, 3404, is_hook=True), _scene("CUTTING", 200, 206), _scene("PLATING", 1800, 1806)]
    )

    analysis = _analyze(monkeypatch, raw, labels=[])

    assert analysis.scenes[0].is_hook and analysis.scenes[0].label == "FINAL_DISH"
    assert [scene.label for scene in analysis.scenes[1:]] == ["CUTTING", "PLATING"]


def test_a_hook_taken_from_the_middle_is_treated_as_an_ordinary_scene(monkeypatch):
    """Only the finished dish earns the out-of-order slot."""
    raw = _response([_scene("SAUTEING", 900, 908, is_hook=True), _scene("CUTTING", 200, 206)])

    analysis = _analyze(monkeypatch, raw, labels=[])

    assert [scene.label for scene in analysis.scenes] == ["CUTTING", "SAUTEING"]
    assert not any(scene.is_hook for scene in analysis.scenes)


def test_scene_durations_are_clamped_to_the_budget_for_their_kind(monkeypatch):
    raw = _response(
        [
            _scene("FINAL_DISH", 3400, 3480, is_hook=True),  # 80s hook
            _scene("CUTTING", 200, 201),  # 1s, too short to read
        ]
    )

    analysis = _analyze(monkeypatch, raw, labels=[])

    hook, cutting = analysis.scenes
    assert 2.0 <= hook.duration <= 4.0
    assert 4.0 <= cutting.duration <= 8.0


def test_uncertain_ingredients_are_demoted_and_scrubbed_from_the_voice_over(monkeypatch):
    """PRD S8: the voice-over must not name something nobody could see."""
    raw = _response(
        [_scene("ADDING_SAUCE", 900, 908, vo_guide="Tambahkan kecap manis secukupnya.")],
        ingredients=[{"name": "ayam", "confidence": 95}, {"name": "kecap manis", "confidence": 30}],
    )

    analysis = _analyze(monkeypatch, raw, labels=[])

    assert [i.name for i in analysis.ingredients] == ["ayam"]
    assert analysis.possible_ingredients == ["kecap manis"]
    assert "kecap manis" not in analysis.scenes[0].vo_guide
    assert "bumbu berikutnya" in analysis.scenes[0].vo_guide


def test_alternatives_come_from_real_labels_only(monkeypatch):
    raw = _response([_scene("CUTTING", 200, 206), _scene("SAUTEING", 900, 908)])

    analysis = _analyze(monkeypatch, raw)

    cutting = analysis.scenes[0]
    # The only other CUTTING moment in the label set is the one it already
    # uses, so there is honestly nothing to offer.
    assert cutting.alternatives == []


def test_a_recipe_too_long_for_the_target_warns_instead_of_dropping_steps(monkeypatch):
    raw = _response([_scene("SAUTEING", 100 * i, 100 * i + 12) for i in range(1, 13)])

    analysis = _analyze(monkeypatch, raw, target=TargetDuration.ONE_MINUTE)

    assert analysis.estimated_duration > 60
    assert any("2-minute" in warning for warning in analysis.warnings)


def test_language_follows_the_transcript_and_falls_back_to_indonesian():
    assert recipe_analyzer.detect_language(_transcript()) == "id"
    assert recipe_analyzer.detect_language(_transcript("then we add the chicken into the pan with some sauce")) == "en"
    assert recipe_analyzer.detect_language(None) == "id"


def test_vo_script_and_text_guide_are_timed_against_the_output(monkeypatch):
    raw = _response([_scene("CUTTING", 200, 206), _scene("PLATING", 1800, 1806)])
    analysis = _analyze(monkeypatch, raw, labels=[])

    script = recipe_analyzer.build_full_vo_script(analysis)
    guide = recipe_analyzer.build_text_guide(analysis)

    assert script.startswith("[0:00-")
    assert "[0:06" in script  # the second scene starts where the first ended
    assert guide.splitlines()[0].startswith("0:00 - AYAM KECAP")


def test_disabled_scenes_are_left_out_of_the_script(monkeypatch):
    raw = _response([_scene("CUTTING", 200, 206), _scene("PLATING", 1800, 1806)])
    analysis = _analyze(monkeypatch, raw, labels=[])
    kept = [analysis.scenes[1]]

    script = recipe_analyzer.build_full_vo_script(analysis, kept)

    assert "CUTTING guide" not in script
    assert "PLATING guide" in script


def test_a_response_with_no_scenes_is_an_empty_analysis_not_a_crash(monkeypatch):
    analysis = _analyze(monkeypatch, _response([]))
    assert analysis.scenes == []
    assert any("cooking steps" in warning for warning in analysis.warnings)


def test_non_object_response_is_rejected(monkeypatch):
    monkeypatch.setattr(recipe_analyzer, "complete_chat", lambda *a, **k: json.dumps([1, 2, 3]))
    with pytest.raises(ValueError):
        recipe_analyzer.analyze_recipe(_PROVIDER, _labels(), _transcript(), TargetDuration.AUTO, [], 3600.0)


def test_cut_points_snap_to_a_nearby_shot_boundary(monkeypatch):
    """A cut should land between actions, not halfway through a knife stroke."""
    segments = [
        VisualSegment(index=0, start=0.0, end=198.0, peak_time=100.0, motion=1.0),
        VisualSegment(index=1, start=198.0, end=260.0, peak_time=210.0, motion=4.0),
    ]
    monkeypatch.setattr(recipe_analyzer, "complete_chat", lambda *a, **k: _response([_scene("CUTTING", 200, 206)]))

    analysis = recipe_analyzer.analyze_recipe(
        _PROVIDER, _labels(), _transcript(), TargetDuration.AUTO, segments, video_duration=3600.0
    )

    assert analysis.scenes[0].source_start == pytest.approx(198.0)


# --- keeping the story whole -------------------------------------------------


def test_scenes_cut_from_the_same_moment_are_not_repeated(monkeypatch):
    """Straight from a real run: three scenes all cut from 254-258s, with
    three different narration lines over the same four seconds, which made the
    video look like it ended abruptly."""
    raw = _response(
        [
            _scene("STIRRING", 243, 248),
            _scene("PREPARATION", 254, 258),
            _scene("PREPARATION", 254, 258),
            _scene("FINAL_DISH", 255, 258),
        ]
    )

    analysis = _analyze(monkeypatch, raw, video_duration=258.0, labels=[])

    ranges = [(s.source_start, s.source_end) for s in analysis.scenes]
    assert len(ranges) == len(set(ranges)), f"duplicate footage in {ranges}"
    for earlier, later in zip(analysis.scenes, analysis.scenes[1:]):
        assert later.source_start >= earlier.source_end, "scenes still overlap"


def test_the_opening_hook_may_still_reuse_the_final_dish(monkeypatch):
    """PRD S11 deliberately shows the finished dish twice."""
    raw = _response(
        [_scene("FINAL_DISH", 3400, 3404, is_hook=True), _scene("CUTTING", 200, 206), _scene("FINAL_DISH", 3400, 3406)]
    )

    analysis = _analyze(monkeypatch, raw, labels=[])

    assert len(analysis.scenes) == 3
    assert analysis.scenes[0].is_hook


def test_a_skipped_stretch_of_cooking_is_put_back(monkeypatch):
    """The 'suddenly finished' complaint: the model jumped from 206s to the
    end, leaving the whole middle of the cook out."""
    raw = _response([_scene("CUTTING", 200, 206)])
    labels = [
        FrameLabel(index=1, time=900.0, label="SAUTEING", confidence=90, action_strength=80, subject="onions"),
        FrameLabel(index=2, time=1800.0, label="SIMMERING", confidence=85, action_strength=70, subject="the pot"),
    ]

    analysis = _analyze(monkeypatch, raw, labels=labels)

    covered = [s.label for s in analysis.scenes]
    assert "SAUTEING" in covered and "SIMMERING" in covered
    assert analysis.scenes == sorted(analysis.scenes, key=lambda s: s.source_start)


def test_gap_filling_stops_at_the_target_and_says_what_it_left_out(monkeypatch):
    raw = _response([_scene("SAUTEING", 100, 112), _scene("FRYING", 200, 212), _scene("BOILING", 300, 312)])
    labels = [
        FrameLabel(index=i, time=600.0 + i * 300, label="STIRRING", confidence=90, action_strength=90)
        for i in range(8)
    ]

    analysis = _analyze(monkeypatch, raw, target=TargetDuration.ONE_MINUTE, labels=labels)

    assert analysis.estimated_duration <= 60 * 1.4
    assert any("left out" in warning for warning in analysis.warnings)


def test_no_scenes_at_all_is_reported_rather_than_filled_in(monkeypatch):
    """An empty result means the model failed; inventing a timeline from
    labels would hide that."""
    analysis = _analyze(monkeypatch, _response([]))

    assert analysis.scenes == []


def test_auto_target_follows_the_length_of_the_source():
    """A four-minute recipe condensed to 37 seconds loses steps it never
    needed to lose."""
    assert recipe_analyzer.auto_target_seconds(258.0) == pytest.approx(77.4)
    assert recipe_analyzer.auto_target_seconds(60.0) == pytest.approx(45.0)  # floor
    assert recipe_analyzer.auto_target_seconds(7200.0) == pytest.approx(120.0)  # ceiling


# --- short-form sources open on the dish -------------------------------------


def test_a_video_that_opens_on_the_finished_dish_treats_it_as_the_hook(monkeypatch):
    """Short-form cooking videos are cut the other way round from the PRD's
    assumption: the hero shot is at the *start*. Read as step one, it put
    'dust with cocoa' at the front of the cooking story."""
    raw = _response(
        [
            _scene("FINAL_DISH", 29, 32),
            _scene("ADDING_MAIN_INGREDIENT", 122, 127),
            _scene("STIRRING", 243, 248),
            _scene("FINAL_DISH", 254, 258),
        ]
    )

    analysis = _analyze(monkeypatch, raw, video_duration=258.0, labels=[])

    assert analysis.scenes[0].is_hook, "the opening dish shot should be the hook"
    assert 2.0 <= analysis.scenes[0].duration <= 4.0
    body = [scene.label for scene in analysis.scenes[1:]]
    assert body == ["ADDING_MAIN_INGREDIENT", "STIRRING", "FINAL_DISH"]


def test_an_intro_montage_is_not_mistaken_for_the_first_cooking_steps(monkeypatch):
    raw = _response(
        [
            _scene("FINISHING", 15, 19),  # admiring the finished truffles
            _scene("FINAL_DISH", 29, 32),
            _scene("MIXING", 146, 150),
            _scene("FINAL_DISH", 254, 258),
        ]
    )

    analysis = _analyze(monkeypatch, raw, video_duration=258.0, labels=[])

    assert analysis.scenes[0].is_hook
    assert "FINISHING" not in [scene.label for scene in analysis.scenes[1:]], "intro shot still in the body"
    assert analysis.scenes[-1].label == "FINAL_DISH", "the story should still end on the dish"


def test_a_dish_shot_with_no_later_equivalent_is_kept(monkeypatch):
    """Dropping it would lose the only view of the finished dish."""
    raw = _response([_scene("FINAL_DISH", 10, 14), _scene("MIXING", 146, 150)])

    analysis = _analyze(monkeypatch, raw, video_duration=258.0, labels=[])

    assert any(scene.label == "FINAL_DISH" for scene in analysis.scenes)


def test_gap_filling_prefers_a_step_the_timeline_does_not_have_yet(monkeypatch):
    """Four more shots of the same pouring action tell the viewer nothing."""
    raw = _response([_scene("ADDING_MAIN_INGREDIENT", 120, 127)])
    labels = [
        FrameLabel(index=1, time=60.0, label="ADDING_MAIN_INGREDIENT", confidence=95, action_strength=95),
        FrameLabel(index=2, time=200.0, label="STIRRING", confidence=70, action_strength=60),
    ]

    analysis = _analyze(monkeypatch, raw, video_duration=258.0, labels=labels)

    labels_used = [scene.label for scene in analysis.scenes]
    assert "STIRRING" in labels_used, f"a new step should win over a stronger repeat: {labels_used}"

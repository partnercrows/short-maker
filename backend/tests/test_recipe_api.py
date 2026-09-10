from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.ai_providers.registry import ProviderConfig, ProviderType
from app.api.recipe import (
    RecipeGenerateRequest,
    RecipeSceneEdit,
    RecipeTimelineRequest,
    generate_recipe_video,
    get_recipe,
    save_timeline,
)
from app.core.config import get_settings
from app.db.connection import get_connection, init_db
from app.pipeline.recipe import recipe_analyzer, store
from app.pipeline.recipe.models import RecipeAnalysis, RecipeScene, SceneFaceCheck, TargetDuration
from app.pipeline.reframe.models import CropWindow, ReframeMode, ReframePlan

_PROVIDER = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")


def _make_recipe_project(project_id: str = "proj-recipe") -> str:
    init_db()
    settings = get_settings()
    source = settings.project_source_path(project_id)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"0" * 512)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, source_duration, status, mode, created_at, updated_at) "
            "VALUES (?, ?, ?, 3600.0, 'queued', 'recipe', 'now', 'now')",
            (project_id, project_id, str(source)),
        )
        conn.commit()
    return project_id


def _plan() -> ReframePlan:
    return ReframePlan(
        mode_used=ReframeMode.FACELESS_COOKING, windows=[CropWindow(time=0.0, x=10, y=0, width=608, height=1080)]
    )


def _scene(scene_id: str, start: float, end: float, label: str = "CUTTING", **extra) -> RecipeScene:
    return RecipeScene(
        scene_id=scene_id,
        order=0,
        label=label,
        title=label.title(),
        source_start=start,
        source_end=end,
        vo_guide=f"{label} guide",
        on_screen_text=label.lower(),
        plan=_plan(),
        face_check=SceneFaceCheck(status="clean"),
        **extra,
    )


def _seed_analysis(project_id: str, scenes: list[RecipeScene]) -> str:
    analysis = RecipeAnalysis(
        recipe_name="Ayam Kecap",
        main_ingredient="Ayam",
        scenes=scenes,
        target_duration=TargetDuration.ONE_MINUTE,
        language="id",
    )
    recipe_analyzer.save_analysis(get_settings().recipe_analysis_path(project_id), analysis)
    clip_id = store.ensure_recipe_clip(project_id, analysis.model_dump_json())
    store.replace_scenes(clip_id, scenes)
    return clip_id


def test_recipe_response_carries_the_timeline_script_and_text_guide():
    project_id = _make_recipe_project()
    _seed_analysis(project_id, [_scene("s1", 100, 106), _scene("s2", 900, 908, "PLATING")])

    recipe = get_recipe(project_id)

    assert recipe.recipe_name == "Ayam Kecap"
    assert [scene.scene_id for scene in recipe.scenes] == ["s1", "s2"]
    assert recipe.estimated_duration == pytest.approx(14.0)
    assert "CUTTING guide" in recipe.vo_script
    assert recipe.text_guide.startswith("0:00 - AYAM KECAP")


def test_the_recipe_video_is_an_ordinary_clip_row():
    """That is what keeps Social Kit, download and deletion working unchanged."""
    project_id = _make_recipe_project()
    clip_id = _seed_analysis(project_id, [_scene("s1", 100, 106)])

    recipe = get_recipe(project_id)

    assert recipe.clip is not None and recipe.clip.id == clip_id
    with get_connection() as conn:
        row = conn.execute("SELECT project_id FROM clips WHERE id = ?", (clip_id,)).fetchone()
    assert row["project_id"] == project_id


def test_reordering_and_dropping_scenes_is_saved_without_touching_the_analysis():
    project_id = _make_recipe_project()
    clip_id = _seed_analysis(project_id, [_scene("s1", 100, 106), _scene("s2", 900, 908), _scene("s3", 1500, 1508)])

    updated = save_timeline(
        project_id,
        RecipeTimelineRequest(
            scenes=[
                RecipeSceneEdit(scene_id="s3", enabled=True),
                RecipeSceneEdit(scene_id="s1", enabled=True),
                RecipeSceneEdit(scene_id="s2", enabled=False),
            ]
        ),
    )

    assert [scene.scene_id for scene in updated.scenes] == ["s3", "s1", "s2"]
    assert [scene.enabled for scene in updated.scenes] == [True, True, False]
    # Reordering must not invalidate the framing work: those scenes still
    # have their crop plans, so regenerating re-encodes nothing.
    assert all(scene.plan is not None for scene in store.load_scenes(clip_id) if scene.scene_id in {"s1", "s3"})


def test_trimming_a_scene_drops_its_stale_crop_plan():
    """The plan was measured against the old range, so it no longer fits."""
    project_id = _make_recipe_project()
    clip_id = _seed_analysis(project_id, [_scene("s1", 100, 106), _scene("s2", 900, 908)])

    save_timeline(
        project_id,
        RecipeTimelineRequest(
            scenes=[
                RecipeSceneEdit(scene_id="s1", source_start=100, source_end=112, enabled=True),
                RecipeSceneEdit(scene_id="s2", enabled=True),
            ]
        ),
    )

    scenes = {scene.scene_id: scene for scene in store.load_scenes(clip_id)}
    assert scenes["s1"].plan is None  # will be rebuilt on the next render
    assert scenes["s2"].plan is not None  # untouched scene keeps its framing


def test_emptying_the_timeline_is_refused():
    project_id = _make_recipe_project()
    _seed_analysis(project_id, [_scene("s1", 100, 106)])

    with pytest.raises(HTTPException) as exc_info:
        save_timeline(project_id, RecipeTimelineRequest(scenes=[RecipeSceneEdit(scene_id="s1", enabled=False)]))
    assert exc_info.value.status_code == 400


def test_generating_before_analyzing_says_so():
    project_id = _make_recipe_project()

    with pytest.raises(HTTPException) as exc_info:
        generate_recipe_video(project_id, RecipeGenerateRequest())
    assert exc_info.value.status_code == 400
    assert "Analyze" in exc_info.value.detail


def test_unknown_project_is_404():
    init_db()
    with pytest.raises(HTTPException) as exc_info:
        get_recipe("nope")
    assert exc_info.value.status_code == 404


def test_a_recipe_project_reports_its_mode_to_the_ui():
    project_id = _make_recipe_project()
    recipe = get_recipe(project_id)
    assert recipe.project.mode == "recipe"


def test_social_kit_uses_the_recipe_prompt_for_a_recipe_project(monkeypatch):
    from app.api import social_kit as social_kit_api

    project_id = _make_recipe_project()
    clip_id = _seed_analysis(project_id, [_scene("s1", 100, 106), _scene("s2", 900, 908, "PLATING")])

    used = {}

    def fake_recipe_kit(config, summary, platform, language):
        used["summary"] = summary
        used["language"] = language
        from app.pipeline.social_kit import RecipeSocialKitExtras, SocialKitContent, TitleOption

        return (
            SocialKitContent(
                titles=[TitleOption(title="Ayam Kecap Simpel", score=90)],
                description="deskripsi",
                hashtags=["ayamkecap"],
                thumbnail_idea="idea",
                thumbnail_prompt="prompt",
            ),
            RecipeSocialKitExtras(alternative_hooks=["hook"], cta="Simpan dulu", thumbnail_text="AYAM KECAP"),
        )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("a recipe must not use the clip prompt")

    monkeypatch.setattr(social_kit_api, "generate_recipe_social_kit", fake_recipe_kit)
    monkeypatch.setattr(social_kit_api, "generate_social_kit", fail_if_called)

    kit = social_kit_api._generate_and_save(clip_id, "youtube_shorts", _PROVIDER)

    assert "Ayam Kecap" in used["summary"]
    assert "Cutting -> Plating" in used["summary"]
    assert used["language"] == "id"
    assert json.loads(kit.extra_json)["cta"] == "Simpan dulu"


def test_social_kit_still_uses_the_clip_prompt_for_an_ai_clipper_clip(monkeypatch):
    """AI Clipper's Social Kit must be exactly what it was."""
    from app.api import social_kit as social_kit_api
    from app.pipeline.social_kit import SocialKitContent, TitleOption

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
            "VALUES ('proj-clip', 'clip', 'v.mp4', 'queued', 'now', 'now')"
        )
        conn.execute(
            "INSERT INTO clips (id, project_id, start_time, end_time, duration, analysis_json, status, created_at, updated_at) "
            "VALUES ('clip-1', 'proj-clip', 0, 10, 10, ?, 'completed', 'now', 'now')",
            (json.dumps({"suggested_title": "A hot take", "reason": "it hooks"}),),
        )
        conn.commit()

    monkeypatch.setattr(
        social_kit_api,
        "generate_social_kit",
        lambda *a, **k: SocialKitContent(
            titles=[TitleOption(title="t", score=1)],
            description="d",
            hashtags=["h"],
            thumbnail_idea="i",
            thumbnail_prompt="p",
        ),
    )
    monkeypatch.setattr(
        social_kit_api,
        "generate_recipe_social_kit",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("clip must not use the recipe prompt")),
    )

    kit = social_kit_api._generate_and_save("clip-1", "tiktok", _PROVIDER)

    assert kit.extra_json is None

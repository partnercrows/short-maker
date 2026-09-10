"""Recipe Clipper endpoints (PRD docs/RECIPE_CLIPER.md).

Thin on purpose: analysis and rendering are jobs, so `/jobs/{id}` polling and
cancellation already work; the project itself is created through the existing
`POST /projects` with `mode="recipe"`, so the source copy, duplicate-name
check and storage accounting are all the ones AI Clipper uses.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.ai_providers.registry import ProviderConfig
from app.api.schemas import Clip, Project
from app.core.config import get_settings
from app.core.security import require_local_token
from app.db.connection import get_connection
from app.jobs.manager import job_manager
from app.jobs.models import Job, JobType
from app.jobs.runners import run_recipe_analyze_job, run_recipe_generate_job
from app.pipeline.recipe import recipe_analyzer, store
from app.pipeline.recipe.models import AudioMode, RecipeScene, TargetDuration

router = APIRouter(prefix="/recipe", tags=["recipe"], dependencies=[Depends(require_local_token)])


class RecipeAnalyzeRequest(BaseModel):
    provider: ProviderConfig
    target_duration: TargetDuration = TargetDuration.AUTO
    faceless: bool = True  # PRD S14: faceless is the default, not an opt-in
    use_gpu: bool = False


class RecipeSceneEdit(BaseModel):
    scene_id: str
    source_start: float | None = None
    source_end: float | None = None
    enabled: bool = True


class RecipeTimelineRequest(BaseModel):
    scenes: list[RecipeSceneEdit]


class RecipeGenerateRequest(BaseModel):
    audio_mode: AudioMode = AudioMode.KEEP
    volume_percent: int = 20
    output_folder: str | None = None


class RecipeResponse(BaseModel):
    project: Project
    clip: Clip | None
    recipe_name: str | None = None
    main_ingredient: str | None = None
    ingredients: list[dict] = []
    possible_ingredients: list[str] = []
    cooking_flow: list[str] = []
    scenes: list[RecipeScene] = []
    estimated_duration: float = 0.0
    target_duration: TargetDuration = TargetDuration.AUTO
    faceless: bool = True
    visual_analysis: str = "ok"
    warnings: list[str] = []
    vo_script: str = ""
    text_guide: str = ""


def _get_project_or_404(project_id: str):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


@router.post("/{project_id}/analyze", response_model=Job)
def analyze_recipe(project_id: str, payload: RecipeAnalyzeRequest) -> Job:
    _get_project_or_404(project_id)
    job = job_manager.create(JobType.ANALYZE_RECIPE, project_id=project_id)
    thread = threading.Thread(
        target=run_recipe_analyze_job,
        args=(job.id, project_id, payload.provider, payload.target_duration.value, payload.faceless, payload.use_gpu),
        daemon=True,
    )
    thread.start()
    return job


@router.get("/{project_id}", response_model=RecipeResponse)
def get_recipe(project_id: str) -> RecipeResponse:
    project_row = _get_project_or_404(project_id)
    settings = get_settings()
    analysis = recipe_analyzer.load_analysis(settings.recipe_analysis_path(project_id))
    clip_id = store.get_recipe_clip_id(project_id)

    clip_row = None
    if clip_id:
        with get_connection() as conn:
            clip_row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()

    # Scenes come from the database, not the analysis file: the file is what
    # the AI said, the table is what the user has since edited.
    scenes = store.load_scenes(clip_id) if clip_id else []
    enabled = [scene for scene in scenes if scene.enabled]

    response = RecipeResponse(
        project=Project(**dict(project_row)),
        clip=Clip(**dict(clip_row)) if clip_row else None,
        scenes=scenes,
        estimated_duration=round(sum(scene.duration for scene in enabled), 2),
    )
    if analysis is not None:
        response.recipe_name = analysis.recipe_name
        response.main_ingredient = analysis.main_ingredient
        response.ingredients = [{"name": i.name, "confidence": i.confidence} for i in analysis.ingredients]
        response.possible_ingredients = analysis.possible_ingredients
        response.cooking_flow = analysis.cooking_flow
        response.target_duration = analysis.target_duration
        response.faceless = analysis.faceless
        response.visual_analysis = analysis.visual_analysis
        response.warnings = analysis.warnings
        response.vo_script = recipe_analyzer.build_full_vo_script(analysis, enabled)
        response.text_guide = recipe_analyzer.build_text_guide(analysis, enabled)
    return response


@router.put("/{project_id}/timeline", response_model=RecipeResponse)
def save_timeline(project_id: str, payload: RecipeTimelineRequest) -> RecipeResponse:
    _get_project_or_404(project_id)
    clip_id = store.get_recipe_clip_id(project_id)
    if clip_id is None:
        raise HTTPException(status_code=400, detail="Analyze this video before editing its timeline.")
    if not any(edit.enabled for edit in payload.scenes):
        raise HTTPException(status_code=400, detail="Keep at least one scene in the timeline.")

    store.apply_timeline_edits(clip_id, [edit.model_dump(exclude_none=True) for edit in payload.scenes])
    return get_recipe(project_id)


@router.post("/{project_id}/generate", response_model=Job)
def generate_recipe_video(project_id: str, payload: RecipeGenerateRequest) -> Job:
    _get_project_or_404(project_id)
    clip_id = store.get_recipe_clip_id(project_id)
    if clip_id is None:
        raise HTTPException(status_code=400, detail="Analyze this video before generating the recipe video.")

    job = job_manager.create(JobType.GENERATE_RECIPE_VIDEO, project_id=project_id)
    thread = threading.Thread(
        target=run_recipe_generate_job,
        args=(job.id, clip_id, payload.audio_mode.value, payload.volume_percent, payload.output_folder),
        daemon=True,
    )
    thread.start()
    return job

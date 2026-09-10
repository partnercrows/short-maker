"""Reading and writing the recipe timeline.

The recipe video is an ordinary `clips` row -- that is what lets Social Kit,
copy-to-folder, storage accounting and cascade delete keep working with no
changes at all. Its scenes live in `recipe_scenes`, one row each, ordered by
`position`, which is the thing the timeline editor reorders.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.pipeline.recipe.models import RecipeScene, SceneAlternative, SceneFaceCheck
from app.pipeline.reframe.models import ReframePlan

RECIPE_CLIP_STATUS_READY = "timeline_ready"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_recipe_clip_id(project_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM clips WHERE project_id = ? ORDER BY created_at LIMIT 1", (project_id,)
        ).fetchone()
    return row["id"] if row else None


def ensure_recipe_clip(project_id: str, analysis_json: str) -> str:
    """One recipe video per project: created on the first analysis, reused
    (and its scenes replaced) by every later one."""
    now = _now()
    existing = get_recipe_clip_id(project_id)
    with get_connection() as conn:
        if existing:
            conn.execute(
                "UPDATE clips SET analysis_json = ?, status = ?, updated_at = ? WHERE id = ?",
                (analysis_json, RECIPE_CLIP_STATUS_READY, now, existing),
            )
            conn.commit()
            return existing

        clip_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO clips (
                id, project_id, start_time, end_time, duration, score,
                analysis_json, status, created_at, updated_at
            ) VALUES (?, ?, 0, 0, 0, NULL, ?, ?, ?, ?)
            """,
            (clip_id, project_id, analysis_json, RECIPE_CLIP_STATUS_READY, now, now),
        )
        conn.commit()
    return clip_id


def replace_scenes(clip_id: str, scenes: list[RecipeScene]) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute("DELETE FROM recipe_scenes WHERE clip_id = ?", (clip_id,))
        for position, scene in enumerate(scenes):
            conn.execute(
                """
                INSERT INTO recipe_scenes (
                    id, clip_id, position, label, title, source_start, source_end, is_hook,
                    vo_guide, on_screen_text, reason, enabled, plan_json, face_check_json,
                    alternatives_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene.scene_id,
                    clip_id,
                    position,
                    scene.label,
                    scene.title,
                    scene.source_start,
                    scene.source_end,
                    1 if scene.is_hook else 0,
                    scene.vo_guide,
                    scene.on_screen_text,
                    scene.reason,
                    1 if scene.enabled else 0,
                    scene.plan.model_dump_json() if scene.plan else None,
                    scene.face_check.model_dump_json() if scene.face_check else None,
                    json.dumps([json.loads(a.model_dump_json()) for a in scene.alternatives]),
                    now,
                    now,
                ),
            )
        conn.commit()


def load_scenes(clip_id: str) -> list[RecipeScene]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM recipe_scenes WHERE clip_id = ? ORDER BY position", (clip_id,)
        ).fetchall()
    return [_row_to_scene(row) for row in rows]


def _row_to_scene(row) -> RecipeScene:
    return RecipeScene(
        scene_id=row["id"],
        order=row["position"],
        label=row["label"],
        title=row["title"] or row["label"],
        source_start=row["source_start"],
        source_end=row["source_end"],
        is_hook=bool(row["is_hook"]),
        vo_guide=row["vo_guide"] or "",
        on_screen_text=row["on_screen_text"] or "",
        reason=row["reason"] or "",
        enabled=bool(row["enabled"]),
        plan=_load_model(ReframePlan, row["plan_json"]),
        face_check=_load_model(SceneFaceCheck, row["face_check_json"]),
        alternatives=_load_alternatives(row["alternatives_json"]),
    )


def _load_model(model, raw: str | None):
    if not raw:
        return None
    try:
        return model.model_validate_json(raw)
    except ValueError:
        return None


def _load_alternatives(raw: str | None) -> list[SceneAlternative]:
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [SceneAlternative(**row) for row in rows if isinstance(row, dict)]


def apply_timeline_edits(clip_id: str, edits: list[dict]) -> list[RecipeScene]:
    """Applies the editor's changes: new order, trims, and which scenes stay.

    Only these three things are editable by design -- Recipe Clipper is a
    clipping tool, not a video editor (PRD S19). Anything the editor does not
    mention is left exactly as the analysis produced it.
    """
    scenes = {scene.scene_id: scene for scene in load_scenes(clip_id)}
    ordered: list[RecipeScene] = []
    for position, edit in enumerate(edits):
        scene = scenes.get(str(edit.get("scene_id")))
        if scene is None:
            continue
        start = float(edit.get("source_start", scene.source_start))
        end = float(edit.get("source_end", scene.source_end))
        if end - start < 0.5:
            end = start + 0.5
        trimmed = start != scene.source_start or end != scene.source_end
        scene.source_start = round(start, 2)
        scene.source_end = round(end, 2)
        scene.enabled = bool(edit.get("enabled", scene.enabled))
        scene.order = position
        if trimmed:
            # The crop path was measured against the old range, so it no
            # longer describes this scene; the next render rebuilds it.
            scene.plan = None
            scene.face_check = None
        ordered.append(scene)

    # Scenes the editor did not mention keep their place at the end rather
    # than silently disappearing.
    for scene in scenes.values():
        if scene not in ordered:
            scene.order = len(ordered)
            ordered.append(scene)

    replace_scenes(clip_id, ordered)
    return ordered


def set_clip_video(clip_id: str, video_path: str, duration: float) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE clips SET video_path = ?, duration = ?, end_time = ?, status = 'completed', updated_at = ? "
            "WHERE id = ?",
            (video_path, duration, duration, _now(), clip_id),
        )
        conn.commit()


def project_mode(project_id: str) -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT mode FROM projects WHERE id = ?", (project_id,)).fetchone()
    return (row["mode"] if row and row["mode"] else "ai_clipper") if row else "ai_clipper"

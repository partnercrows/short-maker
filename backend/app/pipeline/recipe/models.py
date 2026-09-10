"""Data shapes for Recipe Clipper (PRD S7, S9, S18, S27).

Recipe Clipper condenses one long cooking video into a single 1-2 minute
vertical video. Where AI Clipper produces several independent clips scored on
virality, this produces one ordered *story*: hook, preparation, cooking,
transformation, plating. These models carry that story from the analysis
passes through the editable timeline and into the renderer.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app.pipeline.reframe.models import ReframePlan

# PRD S9. The model must pick from this list rather than inventing labels, so
# the timeline can reason about them (hook placement, duration budget) instead
# of pattern-matching free text. OTHER is the escape hatch for everything that
# is not a cooking step -- talking head, camera setup, walking about -- and is
# what lets the selector throw material away with confidence.
SCENE_LABELS = [
    "FINAL_DISH",
    "INGREDIENT",
    "PREPARATION",
    "WASHING",
    "PEELING",
    "CUTTING",
    "CHOPPING",
    "MARINATING",
    "MIXING",
    "SAUTEING",
    "FRYING",
    "BOILING",
    "GRILLING",
    "STEAMING",
    "ADDING_MAIN_INGREDIENT",
    "ADDING_SEASONING",
    "ADDING_SAUCE",
    "STIRRING",
    "SIMMERING",
    "COOKING_PROGRESS",
    "CHECKING_DONENESS",
    "FINISHING",
    "PLATING",
    "SERVING",
    "OTHER",
]

# PRD S13: scenes are not equal length. A hook is a glance; an important
# cooking action needs long enough to read. Keyed by label, falling back to
# _DEFAULT_SCENE_DURATION for anything unlisted.
SCENE_DURATION_RANGES: dict[str, tuple[float, float]] = {
    "FINAL_DISH": (3.0, 6.0),
    "INGREDIENT": (4.0, 7.0),
    "PREPARATION": (4.0, 7.0),
    "WASHING": (3.0, 6.0),
    "PEELING": (4.0, 7.0),
    "CUTTING": (4.0, 8.0),
    "CHOPPING": (4.0, 8.0),
    "MARINATING": (4.0, 8.0),
    "MIXING": (4.0, 8.0),
    "SAUTEING": (6.0, 12.0),
    "FRYING": (6.0, 12.0),
    "BOILING": (5.0, 10.0),
    "GRILLING": (6.0, 12.0),
    "STEAMING": (5.0, 10.0),
    "ADDING_MAIN_INGREDIENT": (5.0, 10.0),
    "ADDING_SEASONING": (5.0, 10.0),
    "ADDING_SAUCE": (5.0, 10.0),
    "STIRRING": (4.0, 8.0),
    "SIMMERING": (5.0, 10.0),
    "COOKING_PROGRESS": (5.0, 10.0),
    "CHECKING_DONENESS": (4.0, 8.0),
    "FINISHING": (4.0, 8.0),
    "PLATING": (4.0, 7.0),
    "SERVING": (3.0, 6.0),
}
_DEFAULT_SCENE_DURATION = (4.0, 8.0)
HOOK_DURATION_RANGE = (2.0, 4.0)  # PRD S11: the final-dish hook is a glance, not a scene


def duration_range_for(label: str, *, is_hook: bool = False) -> tuple[float, float]:
    if is_hook:
        return HOOK_DURATION_RANGE
    return SCENE_DURATION_RANGES.get(label.upper(), _DEFAULT_SCENE_DURATION)


class TargetDuration(StrEnum):
    ONE_MINUTE = "1min"
    TWO_MINUTES = "2min"
    AUTO = "auto"

    @property
    def seconds(self) -> float | None:
        """None for AUTO -- the AI decides from the recipe's complexity."""
        if self is TargetDuration.ONE_MINUTE:
            return 60.0
        if self is TargetDuration.TWO_MINUTES:
            return 120.0
        return None


class AudioMode(StrEnum):
    KEEP = "keep"
    LOWER = "lower"
    MUTE = "mute"


class VisualSegment(BaseModel):
    """One shot of the source video, found locally (no AI) by the frame
    sampler. These are the candidates keyframes are drawn from."""

    index: int
    start: float
    end: float
    peak_time: float  # where the most motion happens inside the shot
    motion: float
    distinctness: float = 0.0
    frame_path: Path | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class FrameLabel(BaseModel):
    """What the vision pass saw in one sampled frame."""

    index: int
    time: float
    label: str
    subject: str = ""
    action_strength: int = 0
    food_visible: bool = True
    face_visible: bool = False
    confidence: int = 0
    ingredients: list[str] = []
    note: str = ""


class SceneAlternative(BaseModel):
    """A different place in the source showing the same step (PRD S20).

    Computed in Python from the label set rather than asked of the model, so
    a "Replace Scene" offer can never point at a timestamp that was invented.
    """

    start: float
    end: float
    label: str
    confidence: int = 0
    subject: str = ""


class SceneFaceCheck(BaseModel):
    """Result of the faceless validation pass (PRD S17, S45)."""

    status: str = "clean"  # clean | reframed | warning
    face_frame_ratio: float = 0.0
    worst_overlap: float = 0.0
    strategy_used: str = "dynamic_crop"
    message: str | None = None


class RecipeScene(BaseModel):
    scene_id: str
    order: int
    label: str
    title: str
    source_start: float
    source_end: float
    is_hook: bool = False
    vo_guide: str = ""
    on_screen_text: str = ""
    reason: str = ""
    enabled: bool = True
    plan: ReframePlan | None = None
    face_check: SceneFaceCheck | None = None
    alternatives: list[SceneAlternative] = []

    @property
    def duration(self) -> float:
        return max(0.0, self.source_end - self.source_start)


class RecipeIngredient(BaseModel):
    name: str
    confidence: int = 0
    uncertain: bool = False


class RecipeAnalysis(BaseModel):
    """Everything the analysis job learned, persisted to
    `analysis/recipe/recipe_analysis.json` so editing, reordering and
    re-rendering never re-spend AI budget (PRD S46)."""

    recipe_name: str | None = None
    main_ingredient: str | None = None
    ingredients: list[RecipeIngredient] = []
    possible_ingredients: list[str] = []
    cooking_flow: list[str] = []
    scenes: list[RecipeScene] = []
    language: str = "id"
    target_duration: TargetDuration = TargetDuration.AUTO
    faceless: bool = True
    visual_analysis: str = "ok"  # ok | unavailable
    warnings: list[str] = []

    @property
    def estimated_duration(self) -> float:
        return sum(scene.duration for scene in self.scenes if scene.enabled)

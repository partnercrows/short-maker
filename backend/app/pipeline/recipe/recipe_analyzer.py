"""Pass 2: turning labelled frames into one cooking story (PRD S7, S10-S13).

AI Clipper looks for hot moments. This looks for a *sequence*: what is being
cooked, what happened first, what changed, how it ended. The model proposes
that sequence; Python then enforces everything the model cannot be trusted
with -- chronology, durations, cut placement, and above all not naming an
ingredient nobody can see (PRD S8).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from app.ai_providers.registry import ProviderConfig, complete_chat
from app.pipeline.ai_analysis.json_utils import extract_json
from app.pipeline.recipe.models import (
    SCENE_LABELS,
    FrameLabel,
    RecipeAnalysis,
    RecipeIngredient,
    RecipeScene,
    SceneAlternative,
    TargetDuration,
    VisualSegment,
    duration_range_for,
)
from app.pipeline.transcribe import TranscriptResult

MIN_SCENES = 4
MAX_SCENES = 24
# Below this the model is guessing rather than reporting, so the ingredient is
# demoted to "possible" and scrubbed out of the spoken guide (PRD S8).
INGREDIENT_CONFIDENCE_FLOOR = 60
# A hook may only be lifted from the end of the video -- that is the finished
# dish. Anything earlier is just a scene out of order (PRD S11).
HOOK_MIN_POSITION = 0.7
_TRANSCRIPT_CHAR_BUDGET = 30000
# Two scenes covering the same seconds are the same footage twice. Beyond this
# much shared time the later one is a duplicate, not a second look.
OVERLAP_DROP_RATIO = 0.5
# A stretch of source this large with cooking in it and no scene covering it is
# a missing step, not an edit.
COVERAGE_GAP_FRACTION = 0.12
MIN_GAP_LABELS = 2
# "Auto" aims for a share of the source rather than a fixed minute: a
# four-minute recipe condensed to 37 seconds loses steps that a four-minute
# recipe does not need to lose.
AUTO_TARGET_SHARE = 0.3
AUTO_TARGET_MIN = 45.0
AUTO_TARGET_MAX = 120.0


def auto_target_seconds(video_duration: float) -> float:
    return max(AUTO_TARGET_MIN, min(AUTO_TARGET_MAX, video_duration * AUTO_TARGET_SHARE))


def target_seconds_for(target: TargetDuration, video_duration: float) -> float:
    return target.seconds if target.seconds is not None else auto_target_seconds(video_duration)

_SYSTEM_PROMPT = """You are editing one long cooking video down to a single short vertical video that \
tells the whole cooking story.

You are given a table of labelled moments from the video (with timestamps), and the transcript if the \
video has speech. Choose the moments that a viewer needs in order to understand the recipe, in the order \
they happen.

Rules:
- Tell the story in chronological order: preparation, then cutting, then seasoning, then cooking, then \
the important change, then finishing, then plating, then the finished dish.
- You MAY open with a 2-4 second shot of the finished dish as a hook. That is the only moment allowed \
out of order. Mark it with "is_hook": true.
- Cut out waiting, idle time, repeated stirring, repeated explanation, walking, searching for utensils, \
camera setup, and long cooking with no visible change. Compressing time is the entire job.
- Do not repeat the same step twice unless something visibly changed.
- Aim for a total of about {target}. Going over by ten or twenty seconds is fine if a step would \
otherwise be lost; losing a step to hit the number exactly is not.
- Only use timestamps that appear in the moments table.
- "vo_guide" is one short sentence the creator will read aloud over that scene. It must be sayable \
within the scene's length: roughly 2-3 words per second, so a 4 second scene is at most ~10 words.
- "on_screen_text" is at most 4 words for the same scene.
- Write "recipe_name", "vo_guide" and "on_screen_text" in {language}.
- Never name an ingredient that is not visible in the moments or named in the speech. If you are not \
sure, say "bumbu berikutnya" / "the next seasoning" instead of naming it, and leave it out of \
"ingredients".
- Respond with ONLY a JSON object, no commentary, in exactly this shape:
{{"recipe_name": "<text or null>", "main_ingredient": "<text or null>", \
"ingredients": [{{"name": "<text>", "confidence": <0-100>}}], \
"cooking_flow": ["<step>"], \
"scenes": [{{"label": "<LABEL>", "title": "<short title>", "start": <seconds>, "end": <seconds>, \
"is_hook": <bool>, "vo_guide": "<one sentence>", "on_screen_text": "<max 4 words>", "reason": "<why it matters>"}}]}}

Allowed labels: {labels}
"""


def analyze_recipe(
    config: ProviderConfig,
    labels: list[FrameLabel],
    transcript: TranscriptResult | None,
    target_duration: TargetDuration,
    segments: list[VisualSegment],
    video_duration: float,
    faceless: bool = True,
    on_model_switch=None,
) -> RecipeAnalysis:
    language = detect_language(transcript)
    system_prompt = _SYSTEM_PROMPT.format(
        target=_target_phrase(target_duration, video_duration),
        language="Indonesian" if language == "id" else "the same language as the transcript",
        labels=" | ".join(SCENE_LABELS),
    )
    raw = complete_chat(
        config, system_prompt, _build_user_prompt(labels, transcript, segments), on_model_switch=on_model_switch
    )
    parsed = extract_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a recipe object, got: {type(parsed)}")

    analysis = RecipeAnalysis(
        recipe_name=_clean_text(parsed.get("recipe_name")),
        main_ingredient=_clean_text(parsed.get("main_ingredient")),
        cooking_flow=[str(step)[:80] for step in (parsed.get("cooking_flow") or [])][:16],
        language=language,
        target_duration=target_duration,
        faceless=faceless,
        visual_analysis="ok" if labels else "unavailable",
    )
    analysis.scenes = _build_scenes(parsed.get("scenes") or [], video_duration, segments)
    analysis.scenes = _drop_overlapping_scenes(analysis.scenes)
    analysis.warnings.extend(
        _fill_coverage_gaps(analysis, labels, target_seconds_for(target_duration, video_duration), video_duration)
    )
    _apply_ingredient_gate(analysis, parsed.get("ingredients") or [], labels)
    _attach_alternatives(analysis, labels)
    analysis.warnings.extend(check_duration_fit(analysis, target_duration, video_duration))
    return analysis


def detect_language(transcript: TranscriptResult | None) -> str:
    """Which language the guides should be written in (PRD examples are
    Indonesian; a silent video has no opinion, so Indonesian wins)."""
    if transcript is None or not transcript.text.strip():
        return "id"
    text = f" {transcript.text.lower()} "
    indonesian_markers = (" dan ", " yang ", " kita ", " sudah ", " tidak ", " ini ", " dengan ", " bumbu ", " masak")
    english_markers = (" the ", " and ", " with ", " then ", " we ", " going ", " into ", " some ")
    id_hits = sum(text.count(marker) for marker in indonesian_markers)
    en_hits = sum(text.count(marker) for marker in english_markers)
    return "en" if en_hits > id_hits else "id"


def _target_phrase(target: TargetDuration, video_duration: float) -> str:
    seconds = target_seconds_for(target, video_duration)
    if target.seconds is None:
        return f"{int(seconds)} seconds -- this source is {int(video_duration)} seconds long, so keep every step"
    return f"{int(seconds)} seconds"


def _build_user_prompt(
    labels: list[FrameLabel], transcript: TranscriptResult | None, segments: list[VisualSegment]
) -> str:
    lines = ["Moments detected in the video:"]
    if labels:
        for label in labels:
            ingredients = f" | sees: {', '.join(label.ingredients)}" if label.ingredients else ""
            face = " | face in shot" if label.face_visible else ""
            lines.append(
                f"[{_mmss(label.time)}] {label.label} (strength {label.action_strength}, "
                f"confidence {label.confidence}) {label.subject}{ingredients}{face}"
            )
    else:
        # Vision was unavailable: hand over the local shot/motion structure so
        # the model still has a timeline to reason about, not just prose.
        lines.append("(no visual labels available -- shot activity only)")
        for segment in segments:
            lines.append(f"[{_mmss(segment.peak_time)}] shot of {segment.duration:.0f}s, activity {segment.motion:.1f}")

    if transcript is not None and transcript.segments:
        lines.append("\nTranscript:")
        spoken = "\n".join(f"[{_mmss(seg.start)}] {seg.text.strip()}" for seg in transcript.segments if seg.text.strip())
        lines.append(spoken[:_TRANSCRIPT_CHAR_BUDGET])
    else:
        lines.append("\nTranscript: (this video has no usable speech)")

    return "\n".join(lines)


def _clean_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text[:120] or None


def _mmss(seconds: float) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:d}:{secs:02d}"


def _build_scenes(rows: list, video_duration: float, segments: list[VisualSegment]) -> list[RecipeScene]:
    scenes: list[RecipeScene] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            start = float(row.get("start"))
            end = float(row.get("end"))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        label = str(row.get("label", "OTHER")).strip().upper()
        is_hook = bool(row.get("is_hook", False))
        start, end = _clamp_duration(start, end, label, is_hook=is_hook, video_duration=video_duration)
        start, end = _snap_to_quiet_moment(start, end, segments)
        scenes.append(
            RecipeScene(
                scene_id=str(uuid.uuid4()),
                order=0,
                label=label if label in SCENE_LABELS else "OTHER",
                title=str(row.get("title", "")).strip()[:80] or label.replace("_", " ").title(),
                source_start=round(start, 2),
                source_end=round(end, 2),
                is_hook=is_hook,
                vo_guide=str(row.get("vo_guide", "")).strip()[:220],
                on_screen_text=str(row.get("on_screen_text", "")).strip()[:60],
                reason=str(row.get("reason", "")).strip()[:220],
            )
        )
    return _enforce_chronology(scenes, video_duration)[:MAX_SCENES]


def _clamp_duration(
    start: float, end: float, label: str, *, is_hook: bool, video_duration: float
) -> tuple[float, float]:
    """Hold each scene to the PRD S13 budget for its kind, and inside the video."""
    low, high = duration_range_for(label, is_hook=is_hook)
    start = max(0.0, min(start, max(0.0, video_duration - low)))
    duration = min(max(end - start, low), high)
    end = min(start + duration, video_duration)
    if end - start < low:
        start = max(0.0, end - low)
    return start, end


def _snap_to_quiet_moment(start: float, end: float, segments: list[VisualSegment], window: float = 2.0) -> tuple[float, float]:
    """Nudge a cut towards a shot boundary within a couple of seconds, so it
    lands between actions instead of halfway through a knife stroke."""
    if not segments:
        return start, end
    boundaries = sorted({segment.start for segment in segments} | {segment.end for segment in segments})
    duration = end - start
    nearest = min(boundaries, key=lambda boundary: abs(boundary - start))
    if abs(nearest - start) <= window:
        start = max(0.0, nearest)
    return start, start + duration


def _enforce_chronology(scenes: list[RecipeScene], video_duration: float) -> list[RecipeScene]:
    """The story runs forwards. Only the opening hook may come from the end.

    Done in Python because a model asked for chronological order will still
    occasionally hand back a shuffled list, and a shuffled cooking video is
    incoherent in a way a shuffled highlight reel is not.
    """
    if not scenes:
        return []
    hook: RecipeScene | None = None
    rest = list(scenes)
    first = rest[0]
    if first.is_hook and video_duration > 0 and first.source_start >= video_duration * HOOK_MIN_POSITION:
        hook = first
        rest = rest[1:]

    # Any other scene claiming to be a hook is just a scene.
    for scene in rest:
        scene.is_hook = False

    ordered = sorted(rest, key=lambda scene: scene.source_start)
    if hook is not None:
        ordered.insert(0, hook)
    for position, scene in enumerate(ordered):
        scene.order = position
    return ordered


def _apply_ingredient_gate(analysis: RecipeAnalysis, rows: list, labels: list[FrameLabel]) -> None:
    """Keep confident ingredients, demote the rest, and take uncertain names
    back out of the spoken guide (PRD S8).

    This is mitigation, not a guarantee -- there is nothing to check the model
    against -- but it stops the obvious failure: a confident-sounding voice
    over telling the viewer to add something that was never in the video.
    """
    seen: set[str] = set()
    for row in rows:
        name = ""
        confidence = 0
        if isinstance(row, dict):
            name = str(row.get("name", "")).strip()
            try:
                confidence = int(row.get("confidence", 0))
            except (TypeError, ValueError):
                confidence = 0
        elif isinstance(row, str):
            name = row.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        uncertain = confidence < INGREDIENT_CONFIDENCE_FLOOR or name.endswith("?")
        clean = name.rstrip("?").strip()
        if uncertain:
            analysis.possible_ingredients.append(clean)
        else:
            analysis.ingredients.append(RecipeIngredient(name=clean, confidence=confidence))

    if not analysis.possible_ingredients:
        return

    generic = "bumbu berikutnya" if analysis.language == "id" else "the next seasoning"
    for scene in analysis.scenes:
        for uncertain_name in analysis.possible_ingredients:
            pattern = re.compile(re.escape(uncertain_name), re.IGNORECASE)
            scene.vo_guide = pattern.sub(generic, scene.vo_guide)
            scene.on_screen_text = pattern.sub("", scene.on_screen_text).strip()


def _attach_alternatives(analysis: RecipeAnalysis, labels: list[FrameLabel], per_scene: int = 3) -> None:
    """Other places in the source showing the same step (PRD S20).

    Built from the label set rather than asked of the model, so a Replace
    Scene offer can never point somewhere that does not exist. Genuinely
    empty when the step was only seen once -- which is the honest answer.
    """
    for scene in analysis.scenes:
        candidates = [
            label
            for label in labels
            if label.label == scene.label and abs(label.time - scene.source_start) >= 20.0
        ]
        candidates.sort(key=lambda label: (-label.confidence, -label.action_strength))
        length = scene.duration
        scene.alternatives = [
            SceneAlternative(
                start=round(max(0.0, label.time - length / 2), 2),
                end=round(max(0.0, label.time - length / 2) + length, 2),
                label=label.label,
                confidence=label.confidence,
                subject=label.subject,
            )
            for label in candidates[:per_scene]
        ]


def _drop_overlapping_scenes(scenes: list[RecipeScene]) -> list[RecipeScene]:
    """Two scenes covering the same seconds show the viewer one clip twice.

    Seen in practice: three consecutive scenes all cut from 254-258s, with
    three different voice-over lines over the same four seconds, which reads
    as the video ending abruptly. The later scene is trimmed to start where
    the earlier one ends, or dropped when almost nothing distinct is left.

    The opening hook is exempt: the PRD deliberately shows the finished dish
    twice, once as a 2-4 second hook and again at the end.
    """
    kept: list[RecipeScene] = []
    for scene in scenes:
        if scene.is_hook:
            kept.append(scene)
            continue
        previous = next((s for s in reversed(kept) if not s.is_hook), None)
        if previous is None or scene.source_start >= previous.source_end:
            kept.append(scene)
            continue

        shared = min(previous.source_end, scene.source_end) - scene.source_start
        shortest = min(previous.duration, scene.duration) or 1.0
        if shared / shortest > OVERLAP_DROP_RATIO:
            continue  # the same moment again

        low, _high = duration_range_for(scene.label, is_hook=False)
        trimmed_start = previous.source_end
        if scene.source_end - trimmed_start < low * 0.6:
            continue
        scene.source_start = round(trimmed_start, 2)
        kept.append(scene)

    for position, scene in enumerate(kept):
        scene.order = position
    return kept


def _fill_coverage_gaps(
    analysis: RecipeAnalysis, labels: list[FrameLabel], target_seconds: float, video_duration: float
) -> list[str]:
    """Puts back steps the model skipped over, while there is room for them.

    A long stretch of source with cooking in it and no scene covering it is
    how a recipe ends up jumping from mixing to finished. Rather than only
    warning about it, the biggest uncovered moment in each gap is added --
    but only while the timeline is still under target, so this can never
    bloat a video past the length that was asked for.
    """
    if not labels or video_duration <= 0 or not analysis.scenes:
        # No scenes at all is the model failing, not a gap in an otherwise
        # sound timeline; the job reports that rather than papering over it.
        return []

    gap_seconds = max(20.0, COVERAGE_GAP_FRACTION * video_duration)
    warnings: list[str] = []

    for _ in range(6):  # bounded: each pass fills at most one gap
        scenes = sorted(analysis.scenes, key=lambda s: s.source_start)
        covered = [(s.source_start, s.source_end) for s in scenes if not s.is_hook]
        gaps = _uncovered_ranges(covered, video_duration, gap_seconds)
        if not gaps:
            break

        candidate = _best_label_in_gaps(labels, gaps)
        if candidate is None:
            break
        if analysis.estimated_duration >= target_seconds:
            start, end = gaps[0]
            warnings.append(
                f"Cooking steps between {_mmss(start)} and {_mmss(end)} were left out to stay near the target "
                "length. Choose a longer target, or add them from the timeline."
            )
            break

        low, high = duration_range_for(candidate.label)
        length = min(high, max(low, (low + high) / 2))
        start = max(0.0, min(candidate.time - length / 2, video_duration - length))
        analysis.scenes.append(
            RecipeScene(
                scene_id=str(uuid.uuid4()),
                order=0,
                label=candidate.label,
                title=candidate.label.replace("_", " ").title(),
                source_start=round(start, 2),
                source_end=round(start + length, 2),
                vo_guide=candidate.subject or candidate.label.replace("_", " ").lower(),
                on_screen_text=candidate.label.replace("_", " ").title(),
                reason="Added to cover a cooking step the first pass skipped over.",
            )
        )
        analysis.scenes = _enforce_chronology(analysis.scenes, video_duration)
        analysis.scenes = _drop_overlapping_scenes(analysis.scenes)

    return warnings


def _uncovered_ranges(
    covered: list[tuple[float, float]], video_duration: float, gap_seconds: float
) -> list[tuple[float, float]]:
    gaps: list[tuple[float, float]] = []
    position = 0.0
    for start, end in covered:
        if start - position >= gap_seconds:
            gaps.append((position, start))
        position = max(position, end)
    if video_duration - position >= gap_seconds:
        gaps.append((position, video_duration))
    return gaps


def _best_label_in_gaps(labels: list[FrameLabel], gaps: list[tuple[float, float]]) -> FrameLabel | None:
    """The most convincing cooking moment inside any uncovered stretch."""
    inside = [
        label
        for label in labels
        if label.label != "OTHER"
        and label.confidence >= 50
        and any(start <= label.time <= end for start, end in gaps)
    ]
    if not inside:
        return None
    return max(inside, key=lambda label: (label.action_strength, label.confidence))


def check_duration_fit(analysis: RecipeAnalysis, target: TargetDuration, video_duration: float = 0.0) -> list[str]:
    """Say so when the recipe does not fit the requested length, instead of
    quietly dropping steps (PRD S44)."""
    warnings: list[str] = []
    if len(analysis.scenes) < MIN_SCENES:
        warnings.append(
            f"Only {len(analysis.scenes)} usable cooking steps were found. This may not be a cooking video, "
            "or the important steps may not be visible enough to detect."
        )
    seconds = target.seconds
    if seconds is not None and analysis.estimated_duration > seconds * 1.35:
        warnings.append(
            f"The AI found {len(analysis.scenes)} important cooking steps, which run to about "
            f"{int(analysis.estimated_duration)} seconds. A {'2-minute' if seconds <= 60 else 'longer'} "
            "output is recommended to keep the whole cooking process. You can still generate this as it is, "
            "or delete scenes in the timeline."
        )
    return warnings


def save_analysis(path: Path, analysis: RecipeAnalysis) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")


def load_analysis(path: Path) -> RecipeAnalysis | None:
    if not Path(path).is_file():
        return None
    try:
        return RecipeAnalysis.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_full_vo_script(analysis: RecipeAnalysis, scenes: list[RecipeScene] | None = None) -> str:
    """The script the creator reads while recording (PRD S23), timed against
    the *output* video rather than the source."""
    lines: list[str] = []
    position = 0.0
    for scene in scenes if scenes is not None else [s for s in analysis.scenes if s.enabled]:
        end = position + scene.duration
        lines.append(f"[{_mmss(position)}-{_mmss(end)}]")
        lines.append(scene.vo_guide or scene.title)
        lines.append("")
        position = end
    return "\n".join(lines).strip()


def build_text_guide(analysis: RecipeAnalysis, scenes: list[RecipeScene] | None = None) -> str:
    """The on-screen text the creator will typeset in Canva (PRD S24, S34).
    Never burned into the video."""
    lines: list[str] = []
    position = 0.0
    for index, scene in enumerate(scenes if scenes is not None else [s for s in analysis.scenes if s.enabled]):
        text = scene.on_screen_text or scene.title
        if index == 0 and analysis.recipe_name:
            text = analysis.recipe_name.upper()
        lines.append(f"{_mmss(position)} - {text}")
        position += scene.duration
    return "\n".join(lines)


def dumps_scene(scene: RecipeScene) -> str:
    return json.dumps(json.loads(scene.model_dump_json()))

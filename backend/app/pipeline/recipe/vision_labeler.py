"""Pass 1 of recipe analysis: what is happening in each sampled frame.

This is the only step that costs image tokens, so it is deliberately a *map*:
each batch of frames is labelled independently, the result is cached on disk,
and every later step (timeline assembly, re-analysis at a different target
duration, Replace Scene alternatives) reads that cache instead of looking at
the video again (PRD S46).

Speech is folded in here rather than kept for later: the transcript lines
around a frame cost almost nothing next to the image and are often what
disambiguates "stirring" from "adding sauce" (PRD S6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from app.ai_providers.registry import ImagePart, ProviderConfig, PromptPart, complete_chat_multimodal
from app.pipeline.ai_analysis.json_utils import extract_json
from app.pipeline.recipe.models import SCENE_LABELS, FrameLabel, VisualSegment
from app.pipeline.recipe.vision_capability import VisionUnsupportedError, classify_vision_failure
from app.pipeline.transcribe import TranscriptResult

VISION_BATCH_SIZE = 12
SPEECH_WINDOW_SECONDS = 8.0

_SYSTEM_PROMPT = """You are watching stills from one cooking video and labelling what each frame shows.

For every frame you are given, return one object with:
- "i": the frame number you were given
- "label": exactly one of: {labels}
- "subject": what is physically visible, in a few words (e.g. "garlic and shallots in a wok")
- "action_strength": 0-100, how much a cooking action is actually happening in this frame
- "food_visible": true/false
- "face_visible": true/false -- true if any human face is visible, even partly
- "confidence": 0-100, how sure you are of the label
- "ingredients": ingredients you can actually see or that the speech names; [] if none are clear
- "note": at most a few words, or ""

Rules:
- Use OTHER for anything that is not a cooking step: a person talking to camera, camera setup, \
walking around, an idle pan with nothing happening, titles.
- Name an ingredient only if you can see it or hear it named. If you are guessing, do not name it. \
Never name a specific brand or a specific regional ingredient you cannot actually identify.
- Judge only what is in the frame; do not infer steps you have not been shown.
- Respond with ONLY a JSON object, no commentary, in exactly this shape:
{{"frames": [{{"i": <int>, "label": "<LABEL>", "subject": "<text>", "action_strength": <int>, \
"food_visible": <bool>, "face_visible": <bool>, "confidence": <int>, "ingredients": ["<text>"], "note": "<text>"}}]}}
"""


def label_frames(
    config: ProviderConfig,
    keyframes: list[VisualSegment],
    transcript: TranscriptResult | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[FrameLabel]:
    """Labels every keyframe, one batch of images per provider call.

    Raises `VisionUnsupportedError` as soon as the model turns out to be
    text-only, so the caller can degrade once instead of failing per batch.
    """
    system_prompt = _SYSTEM_PROMPT.format(labels=" | ".join(SCENE_LABELS))
    batches = [keyframes[i : i + VISION_BATCH_SIZE] for i in range(0, len(keyframes), VISION_BATCH_SIZE)]
    labels: list[FrameLabel] = []

    for batch_number, batch in enumerate(batches):
        parts = _build_parts(batch, transcript)
        if not any(isinstance(part, ImagePart) for part in parts):
            # Every frame in this batch failed to read from disk; skip rather
            # than send a batch of prose about pictures the model can't see.
            continue
        try:
            raw = complete_chat_multimodal(config, system_prompt, parts)
        except Exception as exc:  # noqa: BLE001 -- one specific cause is handled, the rest propagate
            if classify_vision_failure(exc):
                raise VisionUnsupportedError(str(exc)) from exc
            raise
        labels.extend(_parse_batch(raw, batch))
        if on_progress:
            on_progress((batch_number + 1) / len(batches))

    return sorted(labels, key=lambda label: label.time)


def _build_parts(batch: list[VisualSegment], transcript: TranscriptResult | None) -> list[PromptPart]:
    parts: list[PromptPart] = [
        f"Here are {len(batch)} stills from one cooking video, in chronological order.\n"
        "Label each one. The frame number is given before each image."
    ]
    for segment in batch:
        image = _read_frame(segment)
        if image is None:
            continue
        speech = _speech_near(transcript, segment.peak_time)
        header = f"\n[FRAME {segment.index}] t={_timestamp(segment.peak_time)}"
        parts.append(f"{header}  speech nearby: {speech}" if speech else f"{header}  speech nearby: (none)")
        parts.append(ImagePart(data=image))
    return parts


def _read_frame(segment: VisualSegment) -> bytes | None:
    if segment.frame_path is None:
        return None
    path = Path(segment.frame_path)
    try:
        return path.read_bytes()
    except OSError:
        return None


def _speech_near(transcript: TranscriptResult | None, timestamp: float) -> str:
    if transcript is None:
        return ""
    low = timestamp - SPEECH_WINDOW_SECONDS
    high = timestamp + SPEECH_WINDOW_SECONDS
    spoken = [segment.text.strip() for segment in transcript.segments if segment.start < high and segment.end > low]
    joined = " ".join(text for text in spoken if text)
    return joined[:220]


def _timestamp(seconds: float) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"


def _parse_batch(raw: str, batch: list[VisualSegment]) -> list[FrameLabel]:
    """Turns one model reply into labels, keeping only frames we actually sent.

    A model that renumbers frames, invents one, or drops a few is common
    enough that the batch is matched back by index rather than by position.
    """
    try:
        parsed = extract_json(raw)
    except ValueError:
        return []
    rows = parsed.get("frames", []) if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list):
        return []

    by_index = {segment.index: segment for segment in batch}
    labels: list[FrameLabel] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("i"))
        except (TypeError, ValueError):
            continue
        segment = by_index.get(index)
        if segment is None:
            continue
        label = str(row.get("label", "OTHER")).strip().upper()
        labels.append(
            FrameLabel(
                index=index,
                time=segment.peak_time,
                label=label if label in SCENE_LABELS else "OTHER",
                subject=str(row.get("subject", ""))[:200],
                action_strength=_clamp_int(row.get("action_strength"), 0, 100),
                food_visible=bool(row.get("food_visible", True)),
                face_visible=bool(row.get("face_visible", False)),
                confidence=_clamp_int(row.get("confidence"), 0, 100),
                ingredients=[str(item)[:60] for item in (row.get("ingredients") or []) if str(item).strip()][:12],
                note=str(row.get("note", ""))[:120],
            )
        )
    return labels


def _clamp_int(value: object, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return low


def save_labels(path: Path, labels: list[FrameLabel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([json.loads(label.model_dump_json()) for label in labels], indent=2), encoding="utf-8")


def load_labels(path: Path) -> list[FrameLabel]:
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [FrameLabel(**row) for row in rows if isinstance(row, dict)]

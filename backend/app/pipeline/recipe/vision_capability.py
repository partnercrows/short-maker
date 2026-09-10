"""Telling "this model cannot see" apart from "this model is busy".

There is no reliable way to *ask* whether a model accepts images: Gemini,
seven OpenAI-compatible vendors and arbitrary custom endpoints all answer
differently, and a name allowlist rots the week OpenRouter adds an alias. So
Recipe Clipper tries, reads the refusal, and degrades honestly -- the same
shape as the "this model is overloaded, here is one that answers" message in
the provider registry.

These refusals are deliberately NOT in the registry's retryable set: a
text-only model will refuse an image just as firmly on the fourth attempt, and
burning 17 seconds of backoff to learn that helps nobody.
"""

from __future__ import annotations

import httpx
from google.genai import errors as genai_errors

from app.ai_providers.registry import (
    ImagePart,
    ProviderConfig,
    ProviderCredentials,
    _list_model_ids,
    complete_chat_multimodal,
)

# A 1x1 white JPEG -- the smallest thing that is unambiguously an image.
_PROBE_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffc2000b080001000101011100ffc40014000100000000000000000000000000000009"
    "ffda0008010100000000013fffd9"
)

_VISION_REFUSAL_MARKERS = (
    "image",
    "vision",
    "multimodal",
    "modality",
    "inline_data",
    "inlinedata",
    "does not support",
    "not supported",
    "unsupported",
    "invalid_type",
    "invalid argument",
)

# Names that plausibly see. Used only to *order* probe candidates -- a model
# is still only believed once it actually answers an image.
_VISION_NAME_HINTS = ("gemini", "gpt-4o", "gpt-5", "vision", "-vl", "llava", "pixtral", "claude", "qwen-vl")
_MAX_VISION_PROBES = 2


class VisionUnsupportedError(RuntimeError):
    """The configured model refused an image payload -- it is text-only."""


def classify_vision_failure(exc: Exception) -> bool:
    """True when the error means "this model cannot read images", rather than
    a transient, auth or quota problem."""
    if isinstance(exc, VisionUnsupportedError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return exc.code in (400, 404, 415, 422) and _mentions_images(str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code not in (400, 404, 415, 422):
            return False
        body = ""
        try:
            body = exc.response.text
        except Exception:  # noqa: BLE001 -- a body we can't read tells us nothing either way
            body = ""
        return _mentions_images(f"{exc} {body}")
    return False


def _mentions_images(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _VISION_REFUSAL_MARKERS)


def find_vision_model(config: ProviderConfig) -> str | None:
    """A model on the same API key that actually answered an image, or None.

    Best-effort and bounded (two one-word probes): this only ever runs on a
    path that has already lost its visual analysis, and must never turn a
    degraded run into a hang or a second failure.
    """
    try:
        creds = ProviderCredentials(
            provider_type=config.provider_type, api_key=config.api_key, base_url=config.base_url
        )
        candidates = [
            model_id
            for model_id in _list_model_ids(creds)
            if model_id != config.model and any(hint in model_id.lower() for hint in _VISION_NAME_HINTS)
        ]
        for model_id in sorted(candidates, key=_probe_rank)[:_MAX_VISION_PROBES]:
            probe = config.model_copy(update={"model": model_id})
            try:
                answer = complete_chat_multimodal(
                    probe, "Answer in one word.", ["Reply with OK.", ImagePart(data=_PROBE_JPEG)]
                )
            except Exception:  # noqa: BLE001 -- this one is out too, try the next
                continue
            if answer.strip():
                return model_id
    except Exception:  # noqa: BLE001 -- listing failed; the caller simply omits the suggestion
        return None
    return None


def _probe_rank(model_id: str) -> tuple[int, int, str]:
    name = model_id.lower()
    return (
        0 if "flash" in name else 1,  # cheapest class first
        1 if ("preview" in name or "lite" in name or "pro" in name) else 0,
        name,
    )


def degraded_message(config: ProviderConfig, alternative: str | None) -> str:
    base = (
        f'The AI model "{config.model}" cannot read images, so the cooking steps were chosen from speech '
        "and on-screen motion only. Results are usually weaker for a cooking video, which is mostly visual."
    )
    if alternative:
        return (
            f'{base} "{alternative}" can read images with the same API key: switch to it under '
            "Settings > AI Model and run Analyze again."
        )
    return f"{base} Switch to a vision-capable model under Settings > AI Model and run Analyze again."

"""AI provider registry (PRD S5-S6).

No vendor is hardcoded: every provider except Gemini speaks the OpenAI
chat-completions wire format, so one adapter covers OpenAI itself,
DeepSeek, Groq, OpenRouter, xAI, Mistral and any custom OpenAI-compatible
endpoint. Gemini uses the native `google-genai` SDK.
`complete_chat()` is the one entry point clip selection (and, later,
Social Kit) calls -- neither needs to know which vendor answered.

API keys are never persisted by this module; callers pass them in per
request, sourced from the OS-keychain-backed secure storage on the Tauri
side (PRD S5/S40).
"""

from __future__ import annotations

import base64
import time
from typing import Callable
from enum import StrEnum

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

# Transient provider overload (Gemini's 503 UNAVAILABLE "high demand", rate
# limits, upstream 5xx) shouldn't fail a whole analyze/generate job outright
# -- a short retry-with-backoff usually rides it out, since these spikes are
# typically seconds-to-a-minute long, not sustained outages.
_RETRY_BACKOFF_SECONDS = [2, 5, 10]
_RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}

# When the retries run out, the raw provider payload ("503 UNAVAILABLE
# {'error': ...}") is what used to reach the user, and it reads like an app
# bug when the actual fix is almost always "pick a different model". These
# drive the replacement message: a probe of the same API key to find a model
# that answers *right now*, named in the error so the fix is one setting away.
_PROBE_PROMPT = "Reply with OK."
_PROBE_SYSTEM_PROMPT = "Answer in one word."
_MAX_MODEL_PROBES = 3
# A 1x1 JPEG: the smallest thing that is unambiguously an image, used to check
# that a stand-in model can actually see before handing it a request full of
# video frames.
_PROBE_IMAGE = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffc2000b080001000101011100ffc40014000100000000000000000000000000000009"
    "ffda0008010100000000013fffd9"
)
# Names that plausibly accept images. Only used to order probe candidates -- a
# model is believed only once it has actually answered one.
_VISION_NAME_HINTS = ("gemini", "gpt-4o", "gpt-5", "vision", "-vl", "llava", "pixtral", "claude", "qwen-vl")
# Model ids that can't serve a chat completion at all, so probing them would
# only burn time on a guaranteed failure.
_NON_CHAT_MODEL_MARKERS = ("image", "tts", "audio", "embed", "veo", "lyria", "imagen", "banana", "research", "guard")

OPENAI_COMPATIBLE_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
}


class ProviderUnavailableError(RuntimeError):
    """The chosen model kept failing with a transient error (overload / rate
    limit) until the retries ran out.

    Separate from the provider's own exception so the message that reaches
    the job row says what the user can do about it, instead of quoting the
    vendor's JSON at them."""


class ProviderType(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    XAI = "xai"
    MISTRAL = "mistral"
    CUSTOM = "custom"


class ProviderConfig(BaseModel):
    provider_type: ProviderType
    model: str
    api_key: str
    base_url: str | None = None


class ImagePart(BaseModel):
    """One image in a multimodal user turn.

    Recipe Clipper has to show the model what is in the pan -- a cooking video
    is mostly visual and often has no useful narration at all -- while every
    existing caller keeps sending plain text."""

    data: bytes
    mime_type: str = "image/jpeg"


# A user turn is an ordered mix of text and images: the text before each image
# is what tells the model which timestamp it is looking at.
PromptPart = str | ImagePart


class ProviderCredentials(BaseModel):
    """Just enough to authenticate -- no model chosen yet. Used to validate an
    API key and list the models it can access, before the user has to pick one."""

    provider_type: ProviderType
    api_key: str
    base_url: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    detail: str


class ModelInfo(BaseModel):
    id: str
    display_name: str


async def test_connection(creds: ProviderCredentials) -> ConnectionTestResult:
    try:
        models = await list_models(creds)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the user as a plain message
        return ConnectionTestResult(ok=False, detail=f"Connection failed: {exc}")
    return ConnectionTestResult(ok=True, detail=f"Connected. {len(models)} model(s) available.")


async def list_models(creds: ProviderCredentials) -> list[ModelInfo]:
    if creds.provider_type == ProviderType.GEMINI:
        return await _list_models_gemini(creds)
    return await _list_models_openai_compatible(creds)


async def _list_models_gemini(creds: ProviderCredentials) -> list[ModelInfo]:
    client = genai.Client(api_key=creds.api_key)
    models: list[ModelInfo] = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
        if actions and "generateContent" not in actions:
            continue
        model_id = (m.name or "").removeprefix("models/")
        if not model_id:
            continue
        models.append(ModelInfo(id=model_id, display_name=m.display_name or model_id))
    return models


async def _list_models_openai_compatible(creds: ProviderCredentials) -> list[ModelInfo]:
    base_url = creds.base_url or OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(creds.provider_type.value)
    if not base_url:
        raise ValueError("Custom providers require a base_url.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {creds.api_key}"},
        )
    response.raise_for_status()
    items = response.json().get("data", [])
    return [ModelInfo(id=item["id"], display_name=item.get("id", "")) for item in items if item.get("id")]


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True  # Gemini 5xx, including the common 503 UNAVAILABLE "high demand"
    if isinstance(exc, genai_errors.ClientError) and exc.code == 429:
        return True  # Gemini rate limit (RESOURCE_EXHAUSTED)
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _RETRYABLE_HTTP_STATUS_CODES:
        return True
    return False


def complete_chat(
    config: ProviderConfig,
    system_prompt: str,
    user_prompt: str,
    on_model_switch: Callable[[str, str], None] | None = None,
) -> str:
    """One vendor-agnostic entry point: send a system+user prompt, get the
    model's text response back. Raises on failure -- callers (clip
    selection, Social Kit) decide how to handle/report that.

    Transparently retries with backoff on a transient provider error
    (rate limit / overload / upstream 5xx); any other error, or exhausting
    the retries, raises immediately -- unless another model on the same key
    can answer, in which case the request is completed with that one and
    `on_model_switch(from_model, to_model)` is called to say so."""
    return _complete_with_retry(config, system_prompt, user_prompt, on_model_switch=on_model_switch)


def complete_chat_multimodal(
    config: ProviderConfig,
    system_prompt: str,
    parts: list[PromptPart],
    on_model_switch: Callable[[str, str], None] | None = None,
) -> str:
    """`complete_chat` with images allowed in the user turn -- same providers,
    same retry and error contract.

    A parts list that turns out to hold no image collapses to the plain-text
    call, so a caller whose frames went missing still travels the identical
    path the rest of the app uses."""
    if not any(isinstance(part, ImagePart) for part in parts):
        return _complete_with_retry(
            config, system_prompt, "".join(str(part) for part in parts), on_model_switch=on_model_switch
        )
    return _complete_with_retry(config, system_prompt, parts, on_model_switch=on_model_switch)


def _complete_with_retry(
    config: ProviderConfig,
    system_prompt: str,
    user_content: str | list[PromptPart],
    on_model_switch: Callable[[str, str], None] | None = None,
) -> str:
    for attempt, delay in enumerate([0, *_RETRY_BACKOFF_SECONDS]):
        if delay:
            time.sleep(delay)
        try:
            return _complete_once(config, system_prompt, user_content)
        except Exception as exc:  # noqa: BLE001 -- re-raised immediately unless retryable
            if not _is_retryable(exc):
                raise
            if attempt == len(_RETRY_BACKOFF_SECONDS):
                return _complete_on_another_model(config, system_prompt, user_content, exc, on_model_switch)
    raise AssertionError("unreachable")  # the loop above always returns or raises


def _complete_on_another_model(
    config: ProviderConfig,
    system_prompt: str,
    user_content: str | list[PromptPart],
    exc: Exception,
    on_model_switch: Callable[[str, str], None] | None,
) -> str:
    """Last resort before giving up: finish the request on a model that is
    actually answering.

    A model being overloaded is the provider's weather, not a decision the
    user made -- and losing a long analysis to it, minutes in, helps nobody.
    We already probe for a working model just to name one in the error; using
    it is strictly better than telling the user to do the same thing by hand.
    The substitution is reported, never silent, and nothing is written back to
    the user's settings.
    """
    needs_vision = isinstance(user_content, list) and any(isinstance(part, ImagePart) for part in user_content)
    alternative = _find_answering_model(config, with_image=needs_vision)
    if alternative:
        try:
            answer = _complete_once(config.model_copy(update={"model": alternative}), system_prompt, user_content)
        except Exception:  # noqa: BLE001 -- the stand-in failed too; report the original problem
            raise ProviderUnavailableError(_unavailable_message(config, exc, alternative)) from exc
        if on_model_switch:
            on_model_switch(config.model, alternative)
        return answer
    raise ProviderUnavailableError(_unavailable_message(config, exc, None)) from exc


def _is_rate_limit(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ClientError) and exc.code == 429:
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _unavailable_message(config: ProviderConfig, exc: Exception, alternative: str | None = None) -> str:
    attempts = 1 + len(_RETRY_BACKOFF_SECONDS)
    cause = (
        "has no quota left for your API key right now"
        if _is_rate_limit(exc)
        else "is overloaded on the provider's side"
    )
    message = (
        f'The AI model "{config.model}" {cause} -- it failed {attempts} times in a row. '
        "This is not a problem with your video or your API key."
    )
    if alternative:
        return (
            f'{message} "{alternative}" answered fine with the same API key just now: '
            "switch to it under Settings > AI Model, then run Analyze again."
        )
    return f"{message} Try again in a few minutes, or pick a different model under Settings > AI Model."


def _find_answering_model(config: ProviderConfig, *, with_image: bool = False) -> str | None:
    """Probes the provider for a model that responds *now*, so the error can
    name a way out rather than just a failure.

    Deliberately best-effort and bounded (a handful of one-word requests):
    this runs on a path that has already failed, and must never turn a bad
    error message into a worse hang or a second exception."""
    try:
        candidates = _probe_candidates(config)
        if with_image:
            candidates = [name for name in candidates if any(hint in name.lower() for hint in _VISION_NAME_HINTS)]
        payload: str | list[PromptPart] = (
            [_PROBE_PROMPT, ImagePart(data=_PROBE_IMAGE)] if with_image else _PROBE_PROMPT
        )
        for model in candidates[:_MAX_MODEL_PROBES]:
            probe = config.model_copy(update={"model": model})
            try:
                if _complete_once(probe, _PROBE_SYSTEM_PROMPT, payload).strip():
                    return model
            except Exception:  # noqa: BLE001 -- this model is out too; try the next
                continue
    except Exception:  # noqa: BLE001 -- listing failed; the message just omits the suggestion
        return None
    return None


def _probe_candidates(config: ProviderConfig) -> list[str]:
    """Models worth probing, best first.

    Chat-capable only, never the model that just failed, and ordered to try
    the ones most likely to have spare capacity: plain "flash"-class models
    before lite/preview variants, and "pro" last -- on a free tier that's the
    one most likely to be rate-limited even when it is up."""
    creds = ProviderCredentials(provider_type=config.provider_type, api_key=config.api_key, base_url=config.base_url)
    model_ids = [m for m in _list_model_ids(creds) if m != config.model]
    usable = [m for m in model_ids if not any(marker in m.lower() for marker in _NON_CHAT_MODEL_MARKERS)]
    return sorted(usable, key=_probe_rank)


def _probe_rank(model_id: str) -> tuple[int, int, int, str]:
    name = model_id.lower()
    return (
        0 if "flash" in name else 1,
        1 if ("lite" in name or "preview" in name) else 0,
        1 if "pro" in name else 0,
        name,
    )


def _list_model_ids(creds: ProviderCredentials) -> list[str]:
    """Sync sibling of `list_models` -- `complete_chat` and everything below
    it is called from job threads, so this path must not need an event loop."""
    if creds.provider_type == ProviderType.GEMINI:
        client = genai.Client(api_key=creds.api_key)
        ids = []
        for model in client.models.list():
            actions = getattr(model, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            model_id = (model.name or "").removeprefix("models/")
            if model_id:
                ids.append(model_id)
        return ids

    base_url = creds.base_url or OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(creds.provider_type.value)
    if not base_url:
        return []
    response = httpx.get(f"{base_url.rstrip('/')}/models", headers={"Authorization": f"Bearer {creds.api_key}"}, timeout=15.0)
    response.raise_for_status()
    return [item["id"] for item in response.json().get("data", []) if item.get("id")]


def _complete_once(config: ProviderConfig, system_prompt: str, user_prompt: str | list[PromptPart]) -> str:
    """One attempt, no retries -- the single place that picks a provider
    adapter, used by the retry loop, the failover and the probes alike."""
    if config.provider_type == ProviderType.GEMINI:
        return _complete_chat_gemini(config, system_prompt, user_prompt)
    return _complete_chat_openai_compatible(config, system_prompt, user_prompt)


def _complete_chat_gemini(config: ProviderConfig, system_prompt: str, user_prompt: str | list[PromptPart]) -> str:
    client = genai.Client(api_key=config.api_key)
    # A text-only request still passes the bare string straight through, so the
    # request AI Clipper sends is the one it has always sent.
    contents = user_prompt if isinstance(user_prompt, str) else _gemini_parts(user_prompt)
    response = client.models.generate_content(
        model=config.model,
        contents=contents,
        config=genai_types.GenerateContentConfig(system_instruction=system_prompt),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return response.text


def _complete_chat_openai_compatible(
    config: ProviderConfig, system_prompt: str, user_prompt: str | list[PromptPart]
) -> str:
    base_url = config.base_url or OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(config.provider_type.value)
    if not base_url:
        raise ValueError("Custom providers require a base_url.")

    is_text_only = isinstance(user_prompt, str)
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt if is_text_only else _openai_content(user_prompt)},
            ],
        },
        # Images are megabytes of base64 and minutes of model time; a text
        # request keeps the timeout it has always had.
        timeout=120.0 if is_text_only else 300.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _gemini_parts(parts: list[PromptPart]) -> list:
    return [
        genai_types.Part.from_text(text=part)
        if isinstance(part, str)
        else genai_types.Part.from_bytes(data=part.data, mime_type=part.mime_type)
        for part in parts
    ]


def _openai_content(parts: list[PromptPart]) -> list[dict]:
    content: list[dict] = []
    for part in parts:
        if isinstance(part, str):
            content.append({"type": "text", "text": part})
            continue
        encoded = base64.b64encode(part.data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{part.mime_type};base64,{encoded}"}})
    return content

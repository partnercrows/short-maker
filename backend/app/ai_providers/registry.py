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

import time
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

OPENAI_COMPATIBLE_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
}


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


def complete_chat(config: ProviderConfig, system_prompt: str, user_prompt: str) -> str:
    """One vendor-agnostic entry point: send a system+user prompt, get the
    model's text response back. Raises on failure -- callers (clip
    selection, Social Kit) decide how to handle/report that.

    Transparently retries with backoff on a transient provider error
    (rate limit / overload / upstream 5xx); any other error, or exhausting
    the retries, raises immediately."""
    for attempt, delay in enumerate([0, *_RETRY_BACKOFF_SECONDS]):
        if delay:
            time.sleep(delay)
        try:
            if config.provider_type == ProviderType.GEMINI:
                return _complete_chat_gemini(config, system_prompt, user_prompt)
            return _complete_chat_openai_compatible(config, system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 -- re-raised immediately unless retryable
            if not _is_retryable(exc) or attempt == len(_RETRY_BACKOFF_SECONDS):
                raise
    raise AssertionError("unreachable")  # the loop above always returns or raises


def _complete_chat_gemini(config: ProviderConfig, system_prompt: str, user_prompt: str) -> str:
    client = genai.Client(api_key=config.api_key)
    response = client.models.generate_content(
        model=config.model,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(system_instruction=system_prompt),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return response.text


def _complete_chat_openai_compatible(config: ProviderConfig, system_prompt: str, user_prompt: str) -> str:
    base_url = config.base_url or OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(config.provider_type.value)
    if not base_url:
        raise ValueError("Custom providers require a base_url.")

    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]

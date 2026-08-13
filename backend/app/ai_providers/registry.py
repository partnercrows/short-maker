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

from enum import StrEnum

import httpx
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

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


class ConnectionTestResult(BaseModel):
    ok: bool
    detail: str


async def test_connection(config: ProviderConfig) -> ConnectionTestResult:
    if config.provider_type == ProviderType.GEMINI:
        try:
            client = genai.Client(api_key=config.api_key)
            client.models.get(model=config.model)
            return ConnectionTestResult(ok=True, detail="Connected.")
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user as a plain message
            return ConnectionTestResult(ok=False, detail=f"Connection failed: {exc}")

    base_url = config.base_url or OPENAI_COMPATIBLE_DEFAULT_BASE_URLS.get(config.provider_type.value)
    if not base_url:
        return ConnectionTestResult(ok=False, detail="Custom providers require a base_url.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {config.api_key}"},
            )
        if response.status_code == 200:
            return ConnectionTestResult(ok=True, detail="Connected.")
        return ConnectionTestResult(ok=False, detail=f"Provider returned HTTP {response.status_code}.")
    except httpx.HTTPError as exc:
        return ConnectionTestResult(ok=False, detail=f"Connection failed: {exc}")


def complete_chat(config: ProviderConfig, system_prompt: str, user_prompt: str) -> str:
    """One vendor-agnostic entry point: send a system+user prompt, get the
    model's text response back. Raises on failure -- callers (clip
    selection, Social Kit) decide how to handle/report that."""
    if config.provider_type == ProviderType.GEMINI:
        return _complete_chat_gemini(config, system_prompt, user_prompt)
    return _complete_chat_openai_compatible(config, system_prompt, user_prompt)


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

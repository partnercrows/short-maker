from __future__ import annotations

import httpx
import pytest
from google.genai import errors as genai_errors

from app.ai_providers import registry
from app.ai_providers.registry import ProviderConfig, ProviderType, ProviderUnavailableError, complete_chat

_GEMINI_CONFIG = ProviderConfig(provider_type=ProviderType.GEMINI, model="fake-model", api_key="fake")
_OPENAI_CONFIG = ProviderConfig(provider_type=ProviderType.OPENAI, model="fake-model", api_key="fake")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # Retries would otherwise take 2+5+10=17s per exhausted-retry test.
    monkeypatch.setattr(registry.time, "sleep", lambda _seconds: None)


def _server_error(code: int = 503, status: str = "UNAVAILABLE") -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"code": code, "status": status, "message": "high demand"}})


def _client_error(code: int, status: str = "INVALID_ARGUMENT") -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"code": code, "status": status, "message": "bad"}})


def test_complete_chat_succeeds_on_first_try(monkeypatch):
    monkeypatch.setattr(registry, "_complete_chat_gemini", lambda *a, **k: "hello")
    assert complete_chat(_GEMINI_CONFIG, "sys", "user") == "hello"


def test_complete_chat_retries_gemini_server_error_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _server_error()
        return "recovered"

    monkeypatch.setattr(registry, "_complete_chat_gemini", fake)
    assert complete_chat(_GEMINI_CONFIG, "sys", "user") == "recovered"
    assert calls["n"] == 3


def test_complete_chat_retries_gemini_rate_limit(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise _client_error(429, "RESOURCE_EXHAUSTED")
        return "recovered"

    monkeypatch.setattr(registry, "_complete_chat_gemini", fake)
    assert complete_chat(_GEMINI_CONFIG, "sys", "user") == "recovered"


def test_complete_chat_does_not_retry_non_retryable_client_error(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        raise _client_error(400, "INVALID_ARGUMENT")

    monkeypatch.setattr(registry, "_complete_chat_gemini", fake)
    with pytest.raises(genai_errors.ClientError):
        complete_chat(_GEMINI_CONFIG, "sys", "user")
    assert calls["n"] == 1  # no retries attempted


def test_complete_chat_raises_only_when_no_model_answers(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        raise _server_error()

    monkeypatch.setattr(registry, "_complete_chat_gemini", fake)
    monkeypatch.setattr(registry, "_find_answering_model", lambda config, **kwargs: None)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        complete_chat(_GEMINI_CONFIG, "sys", "user")
    assert calls["n"] == 1 + len(registry._RETRY_BACKOFF_SECONDS)
    assert "overloaded" in str(exc_info.value)
    assert "Settings > AI Model" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, genai_errors.ServerError)


def test_an_overloaded_model_is_finished_on_one_that_answers(monkeypatch):
    """Losing a long analysis to the provider's weather helps nobody: finish
    the work on a model that is up, and say that is what happened."""
    monkeypatch.setattr(registry, "_list_model_ids", lambda creds: ["gemini-pro-latest", "gemini-3.5-flash"])
    switches = []

    def fake_once(config, system_prompt, user_prompt):
        if config.model == "gemini-3.5-flash":
            return "the real answer"
        raise _server_error()

    monkeypatch.setattr(registry, "_complete_once", fake_once)

    answer = complete_chat(_GEMINI_CONFIG, "sys", "user", on_model_switch=lambda old, new: switches.append((old, new)))

    assert answer == "the real answer"
    assert switches == [("fake-model", "gemini-3.5-flash")]


def test_a_request_with_images_only_fails_over_to_a_model_that_can_see(monkeypatch):
    monkeypatch.setattr(
        registry, "_list_model_ids", lambda creds: ["some-text-only-model", "deepseek-chat", "gemini-3.5-flash"]
    )
    probed = []

    def fake_once(config, system_prompt, user_prompt):
        if config.model == "fake-model":
            raise _server_error()
        probed.append(config.model)
        return "OK"

    monkeypatch.setattr(registry, "_complete_once", fake_once)

    registry.complete_chat_multimodal(_GEMINI_CONFIG, "sys", ["frame", registry.ImagePart(data=b"\xff\xd8")])

    # Only the vision-plausible candidate was ever tried.
    assert probed and all("gemini" in model for model in probed)


def test_when_the_stand_in_also_fails_the_error_names_it(monkeypatch):
    monkeypatch.setattr(registry, "_list_model_ids", lambda creds: ["gemini-3.5-flash"])

    def always_busy(config, system_prompt, user_prompt):
        if user_prompt == registry._PROBE_PROMPT:
            return "OK"  # answers a one-word probe...
        raise _server_error()  # ...but not the real request

    monkeypatch.setattr(registry, "_complete_once", always_busy)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        complete_chat(_GEMINI_CONFIG, "sys", "user")
    assert '"gemini-3.5-flash" answered fine' in str(exc_info.value)


def test_rate_limit_exhaustion_says_quota_rather_than_overload(monkeypatch):
    monkeypatch.setattr(
        registry, "_complete_chat_gemini", lambda *a, **k: (_ for _ in ()).throw(_client_error(429, "RESOURCE_EXHAUSTED"))
    )
    monkeypatch.setattr(registry, "_find_answering_model", lambda config, **kwargs: None)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        complete_chat(_GEMINI_CONFIG, "sys", "user")
    assert "no quota left" in str(exc_info.value)


def test_probe_skips_the_failing_model_and_non_chat_models(monkeypatch):
    monkeypatch.setattr(
        registry, "_list_model_ids", lambda creds: ["fake-model", "gemini-2.5-flash-image", "veo-3", "gemini-3.5-flash"]
    )
    assert registry._probe_candidates(_GEMINI_CONFIG) == ["gemini-3.5-flash"]


def test_find_answering_model_returns_none_when_listing_fails(monkeypatch):
    def boom(creds):
        raise RuntimeError("no network")

    monkeypatch.setattr(registry, "_list_model_ids", boom)
    assert registry._find_answering_model(_GEMINI_CONFIG) is None


def test_complete_chat_retries_openai_compatible_503(monkeypatch):
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("service unavailable", request=request, response=response)
        return "recovered"

    monkeypatch.setattr(registry, "_complete_chat_openai_compatible", fake)
    assert complete_chat(_OPENAI_CONFIG, "sys", "user") == "recovered"
    assert calls["n"] == 2


def test_complete_chat_does_not_retry_openai_compatible_401(monkeypatch):
    def fake(*a, **k):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(registry, "_complete_chat_openai_compatible", fake)
    with pytest.raises(httpx.HTTPStatusError):
        complete_chat(_OPENAI_CONFIG, "sys", "user")

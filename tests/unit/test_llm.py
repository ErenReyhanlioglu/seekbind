"""backend/services/llm.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APIError, APITimeoutError

import backend.services.llm as llm_module
from backend.config import get_settings
from backend.services.cache import CachedLLMProvider
from backend.services.llm import ChatMessage, LLMServiceError, OllamaLLM, OpenAILLM, get_llm_provider

_DUMMY_REQUEST = httpx.Request("POST", "https://example.com")


def _make_completion(
    content: str = "merhaba",
    model: str = "gpt-4o-mini",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


def test_openai_llm_model_matches_configured_setting() -> None:
    provider = OpenAILLM()

    assert provider.model == get_settings().openai_llm_model


def test_ollama_llm_model_matches_configured_setting() -> None:
    provider = OllamaLLM()

    assert provider.model == get_settings().ollama_llm_model


async def test_openai_complete_returns_response_with_content_and_usage() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion(content="merhaba dünya")
    )

    response = await provider.complete([ChatMessage(role="user", content="selam")])

    assert response.content == "merhaba dünya"
    assert response.model == "gpt-4o-mini"
    assert response.provider == "openai"
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 5
    assert response.total_tokens == 15
    assert response.finish_reason == "stop"


async def test_openai_complete_sends_correct_request() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion()
    )

    await provider.complete(
        [ChatMessage(role="system", content="sen bir asistansın"), ChatMessage(role="user", content="selam")],
        temperature=0.2,
        max_tokens=100,
    )

    call = provider._client.chat.completions.create.call_args
    assert call.kwargs["model"] == provider._model
    assert call.kwargs["messages"] == [
        {"role": "system", "content": "sen bir asistansın"},
        {"role": "user", "content": "selam"},
    ]
    assert call.kwargs["temperature"] == 0.2
    assert call.kwargs["max_tokens"] == 100
    assert call.kwargs["timeout"] == provider._timeout_seconds


async def test_openai_complete_forwards_response_format_when_given() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion()
    )

    await provider.complete(
        [ChatMessage(role="user", content="selam")],
        response_format={"type": "json_object"},
    )

    call = provider._client.chat.completions.create.call_args
    assert call.kwargs["response_format"] == {"type": "json_object"}


async def test_openai_complete_forwards_langfuse_name_and_metadata_when_given() -> None:
    """langfuse_name/langfuse_metadata, langfuse.openai.AsyncOpenAI'ın kendi
    sarmalayıcısına name=/metadata= olarak iletilmeli (bkz.
    feature/langfuse-integration) — bu sayede her adım Langfuse'ta ayrı bir
    isimle ve zengin metadata'yla görünür."""
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion()
    )

    await provider.complete(
        [ChatMessage(role="user", content="selam")],
        langfuse_name="intent_parsing",
        langfuse_metadata={"raw_query": "ucuz dişçi"},
    )

    call = provider._client.chat.completions.create.call_args
    assert call.kwargs["name"] == "intent_parsing"
    assert call.kwargs["metadata"] == {"raw_query": "ucuz dişçi"}


async def test_openai_complete_passes_none_langfuse_fields_by_default() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion()
    )

    await provider.complete([ChatMessage(role="user", content="selam")])

    call = provider._client.chat.completions.create.call_args
    assert call.kwargs["name"] is None
    assert call.kwargs["metadata"] is None


async def test_openai_complete_passes_none_response_format_by_default() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion()
    )

    await provider.complete([ChatMessage(role="user", content="selam")])

    call = provider._client.chat.completions.create.call_args
    assert call.kwargs["response_format"] is None


async def test_openai_complete_raises_service_error_on_timeout() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APITimeoutError(request=_DUMMY_REQUEST)
    )

    with pytest.raises(LLMServiceError):
        await provider.complete([ChatMessage(role="user", content="selam")])


async def test_openai_complete_raises_service_error_on_connection_error() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIConnectionError(request=_DUMMY_REQUEST)
    )

    with pytest.raises(LLMServiceError):
        await provider.complete([ChatMessage(role="user", content="selam")])


async def test_openai_complete_raises_service_error_on_api_error() -> None:
    provider = OpenAILLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError("hata", request=_DUMMY_REQUEST, body=None)
    )

    with pytest.raises(LLMServiceError):
        await provider.complete([ChatMessage(role="user", content="selam")])


async def test_openai_close_closes_underlying_client() -> None:
    provider = OpenAILLM()
    provider._client.close = AsyncMock()  # type: ignore[method-assign]

    await provider.close()

    provider._client.close.assert_awaited_once()


def test_openai_semaphore_sized_from_settings() -> None:
    provider = OpenAILLM()
    settings = llm_module.get_settings()

    assert provider._semaphore._value == settings.llm_max_concurrent_calls


def test_ollama_uses_openai_compatible_base_url() -> None:
    provider = OllamaLLM()

    assert str(provider._client.base_url).rstrip("/").endswith("/v1")


async def test_ollama_complete_returns_response_with_content_and_usage() -> None:
    provider = OllamaLLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_completion(content="merhaba", model="qwen3:7b")
    )

    response = await provider.complete([ChatMessage(role="user", content="selam")])

    assert response.provider == "ollama"
    assert response.model == "qwen3:7b"


async def test_ollama_complete_raises_service_error_on_connection_error() -> None:
    provider = OllamaLLM()
    provider._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIConnectionError(request=_DUMMY_REQUEST)
    )

    with pytest.raises(LLMServiceError):
        await provider.complete([ChatMessage(role="user", content="selam")])


async def test_ollama_close_closes_underlying_client() -> None:
    provider = OllamaLLM()
    provider._client.close = AsyncMock()  # type: ignore[method-assign]

    await provider.close()

    provider._client.close.assert_awaited_once()


async def test_complete_defaults_token_counts_to_zero_when_usage_missing() -> None:
    """Ollama'nın bazı sürümleri completion yanıtında `usage` alanını hiç
    döndürmeyebilir — bu durumda token sayıları sessizce 0 olmalı, hata
    fırlatılmamalı."""
    provider = OllamaLLM()
    completion = _make_completion()
    completion.usage = None
    provider._client.chat.completions.create = AsyncMock(return_value=completion)  # type: ignore[method-assign]

    response = await provider.complete([ChatMessage(role="user", content="selam")])

    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0
    assert response.total_tokens == 0


def test_get_llm_provider_returns_openai_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_llm_provider()` artık çıplak `OpenAILLM` değil, Redis cache ile
    sarılmış hâlini döner (bkz. backend/services/cache.py)."""
    real_settings = llm_module.get_settings()
    fake_settings = real_settings.model_copy(update={"active_llm_provider": "openai"})
    monkeypatch.setattr(llm_module, "get_settings", lambda: fake_settings)
    get_llm_provider.cache_clear()

    try:
        provider = get_llm_provider()
        assert isinstance(provider, CachedLLMProvider)
        assert isinstance(provider._inner, OpenAILLM)  # type: ignore[attr-defined]
    finally:
        get_llm_provider.cache_clear()


def test_get_llm_provider_returns_ollama_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_llm_provider()` artık çıplak `OllamaLLM` değil, Redis cache ile
    sarılmış hâlini döner (bkz. backend/services/cache.py)."""
    real_settings = llm_module.get_settings()
    fake_settings = real_settings.model_copy(update={"active_llm_provider": "ollama"})
    monkeypatch.setattr(llm_module, "get_settings", lambda: fake_settings)
    get_llm_provider.cache_clear()

    try:
        provider = get_llm_provider()
        assert isinstance(provider, CachedLLMProvider)
        assert isinstance(provider._inner, OllamaLLM)  # type: ignore[attr-defined]
    finally:
        get_llm_provider.cache_clear()

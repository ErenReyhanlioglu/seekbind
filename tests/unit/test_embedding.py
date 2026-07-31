"""backend/services/embedding.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIError, APITimeoutError

from backend.config import get_settings
from backend.services.cache import CachedEmbeddingProvider
from backend.services.embedding import EmbeddingServiceError, OpenAIEmbedding, get_embedding_provider

_DUMMY_REQUEST = httpx.Request("POST", "https://example.com")


def _make_embedding_response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])


def test_openai_embedding_name_is_openai() -> None:
    provider = OpenAIEmbedding()

    assert provider.name == "openai"


def test_openai_embedding_model_matches_configured_setting() -> None:
    provider = OpenAIEmbedding()

    assert provider.model == get_settings().openai_embedding_model


def test_openai_embedding_dimension_is_1536() -> None:
    provider = OpenAIEmbedding()

    assert provider.dimension == 1536


async def test_openai_embedding_embed_batch_returns_vectors_in_order() -> None:
    provider = OpenAIEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_embedding_response([[0.1, 0.2], [0.3, 0.4]])
    )

    result = await provider.embed_batch(["metin1", "metin2"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_openai_embedding_embed_batch_sends_all_texts_in_one_request() -> None:
    """478 işletmeyi teker teker değil batch olarak embed etmek gerekiyor
    (bkz. CLAUDE.md) — bu test, tüm metinlerin TEK bir API çağrısında
    gönderildiğini doğruluyor."""
    provider = OpenAIEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_embedding_response([[0.1], [0.2]])
    )

    await provider.embed_batch(["metin1", "metin2"])

    call = provider._client.embeddings.create.call_args
    assert call.kwargs["input"] == ["metin1", "metin2"]
    assert call.kwargs["model"] == provider._model


async def test_openai_embedding_raises_service_error_on_timeout() -> None:
    provider = OpenAIEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APITimeoutError(request=_DUMMY_REQUEST)
    )

    with pytest.raises(EmbeddingServiceError):
        await provider.embed_batch(["metin"])


async def test_openai_embedding_raises_service_error_on_api_error() -> None:
    provider = OpenAIEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError("hata", request=_DUMMY_REQUEST, body=None)
    )

    with pytest.raises(EmbeddingServiceError):
        await provider.embed_batch(["metin"])


def test_get_embedding_provider_returns_openai_embedding_wrapped_in_cache() -> None:
    """`get_embedding_provider()` artık çıplak `OpenAIEmbedding` değil,
    Redis cache ile sarılmış hâlini döner (bkz. backend/services/cache.py)."""
    get_embedding_provider.cache_clear()

    try:
        provider = get_embedding_provider()
        assert isinstance(provider, CachedEmbeddingProvider)
        assert isinstance(provider._inner, OpenAIEmbedding)  # type: ignore[attr-defined]
    finally:
        get_embedding_provider.cache_clear()


def test_get_embedding_provider_returns_same_instance_on_repeated_calls() -> None:
    get_embedding_provider.cache_clear()

    try:
        assert get_embedding_provider() is get_embedding_provider()
    finally:
        get_embedding_provider.cache_clear()

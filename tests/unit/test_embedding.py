"""backend/services/embedding.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIError, APITimeoutError

import backend.services.embedding as embedding_module
from backend.config import get_settings
from backend.services.cache import CachedEmbeddingProvider
from backend.services.embedding import EmbeddingServiceError, OllamaEmbedding, OpenAIEmbedding, get_embedding_provider
from backend.services.fallback import FallbackEmbeddingProvider

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


def test_ollama_embedding_name_derives_from_sanitized_model_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.name`, `businesses_ollama-<model>` Qdrant collection'ının adını
    belirler — modele özgü olduğu için farklı boyuttaki iki Ollama modeli
    (örn. qwen3-embedding:0.6b ve embeddingmagibu-200m) asla aynı collection
    adını üretemez (bkz. ADR-0024). Ayrıştırılmış (sanitize edilmiş) beklenen
    değer elle, gerçek sağlayıcının kendi mantığını tekrarlamadan yazılır —
    hem `:` hem `/` hem `.` gibi ayraçları kapsayan bir model adıyla."""
    real_settings = embedding_module.get_settings()
    fake_settings = real_settings.model_copy(update={"ollama_embedding_model": "alibayram/embeddingmagibu-200m"})
    monkeypatch.setattr(embedding_module, "get_settings", lambda: fake_settings)

    provider = OllamaEmbedding()

    assert provider.name == "ollama-alibayram-embeddingmagibu-200m"


def test_ollama_embedding_model_matches_configured_setting() -> None:
    provider = OllamaEmbedding()

    assert provider.model == get_settings().ollama_embedding_model


def test_ollama_embedding_dimension_matches_known_model(monkeypatch: pytest.MonkeyPatch) -> None:
    real_settings = embedding_module.get_settings()
    fake_settings = real_settings.model_copy(update={"ollama_embedding_model": "qwen3-embedding:0.6b"})
    monkeypatch.setattr(embedding_module, "get_settings", lambda: fake_settings)

    provider = OllamaEmbedding()

    assert provider.dimension == 1024


def test_ollama_embedding_raises_value_error_for_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bilinmeyen bir OLLAMA_EMBEDDING_MODEL, yanlış boyutla sessizce devam
    etmek yerine fail-fast bir ValueError fırlatmalı (bkz. embedding.py
    _OLLAMA_EMBEDDING_DIMENSIONS docstring'i, ADR-0024) — az önce gerçek bir
    kurulumda yaşanan 'yanlış boyutla Qdrant collection'ı oluşturma' hatasının
    regresyon testi."""
    real_settings = embedding_module.get_settings()
    fake_settings = real_settings.model_copy(update={"ollama_embedding_model": "bilinmeyen-model:1b"})
    monkeypatch.setattr(embedding_module, "get_settings", lambda: fake_settings)

    with pytest.raises(ValueError):
        OllamaEmbedding()


async def test_ollama_embedding_embed_batch_returns_vectors_in_order() -> None:
    provider = OllamaEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_embedding_response([[0.1, 0.2], [0.3, 0.4]])
    )

    result = await provider.embed_batch(["metin1", "metin2"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]


async def test_ollama_embedding_raises_service_error_on_api_error() -> None:
    provider = OllamaEmbedding()
    provider._client.embeddings.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIError("hata", request=_DUMMY_REQUEST, body=None)
    )

    with pytest.raises(EmbeddingServiceError):
        await provider.embed_batch(["metin"])


async def test_openai_embedding_close_closes_underlying_client() -> None:
    provider = OpenAIEmbedding()
    provider._client.close = AsyncMock()  # type: ignore[method-assign]

    await provider.close()

    provider._client.close.assert_awaited_once()


def test_get_embedding_provider_returns_openai_primary_wrapped_in_fallback_and_cache() -> None:
    """`get_embedding_provider()` artık çıplak `OpenAIEmbedding` değil,
    Redis cache + Ollama fallback ile sarılmış hâlini döner (bkz.
    backend/services/cache.py, backend/services/fallback.py)."""
    get_embedding_provider.cache_clear()

    try:
        provider = get_embedding_provider()
        assert isinstance(provider, FallbackEmbeddingProvider)
        primary = provider._primary  # type: ignore[attr-defined]
        assert isinstance(primary, CachedEmbeddingProvider)
        assert isinstance(primary._inner, OpenAIEmbedding)  # type: ignore[attr-defined]
        secondary = provider._secondary  # type: ignore[attr-defined]
        assert isinstance(secondary, CachedEmbeddingProvider)
        assert isinstance(secondary._inner, OllamaEmbedding)  # type: ignore[attr-defined]
    finally:
        get_embedding_provider.cache_clear()


def test_get_embedding_provider_with_allow_fallback_false_returns_bare_cached_primary() -> None:
    """`scripts.load_embeddings`'in kullandığı yol — toplu yükleme sırasında
    fallback bilinçli olarak devre dışı (bkz. get_embedding_provider docstring'i)."""
    get_embedding_provider.cache_clear()

    try:
        provider = get_embedding_provider(allow_fallback=False)
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

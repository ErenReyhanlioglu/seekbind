"""`backend/services/cache.py` için gerçek Redis'e karşı entegrasyon testleri.

Sahte (ücretsiz) inner provider'lar kullanılır — amaç LLM/embedding
kalitesini değil, cache mekaniğinin (gerçek hit/miss, gerçek TTL yazımı)
gerçek bir Redis'e karşı çalıştığını kanıtlamak. `test_cache.py` (unit)
aynı mekanizmayı bellek-içi bir sahte Redis'e karşı zaten test ediyor —
burası sadece gerçek Redis bağlantısının/protokolünün beklendiği gibi
davrandığını doğruluyor, mükerrer değil.

Tüm test anahtarları ayırt edici bir isim/model öneki (`_NAME`/`_MODEL`)
taşır, testler bitince bu önekle eşleşen her şey silinir — dev Redis'te
kalıcı iz kalmaz.
"""

from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis

from backend.db.redis import get_redis_client
from backend.services.cache import CachedEmbeddingProvider, CachedLLMProvider
from backend.services.llm import ChatMessage, LLMResponse

pytestmark = pytest.mark.integration

_TTL_SECONDS = 30
_NAME = "integration-test-fake"
_MODEL = "integration-test-fake-model"


class _FakeEmbeddingProvider:
    name = _NAME
    model = _MODEL
    dimension = 3

    def __init__(self) -> None:
        self.call_count = 0

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def close(self) -> None:
        pass


class _FakeLLMProvider:
    name = _NAME
    model = _MODEL

    def __init__(self) -> None:
        self.call_count = 0

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        langfuse_name: str | None = None,
        langfuse_metadata: dict[str, object] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        return LLMResponse(
            content="gerçek cevap",
            model=self.model,
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
        )

    async def close(self) -> None:
        pass


@pytest.fixture
async def redis_client() -> AsyncGenerator[Redis, None]:
    """Gerçek Redis client'ı — test bitince bu dosyanın oluşturduğu tüm
    anahtarları (`_NAME` önekiyle) siler, dev Redis'te iz kalmaz."""
    client = get_redis_client()
    try:
        yield client
    finally:
        async for key in client.scan_iter(match=f"*{_NAME}*"):
            await client.delete(key)


async def test_cached_embedding_provider_serves_second_identical_call_from_real_redis(
    redis_client: Redis,
) -> None:
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, redis_client, enabled=True, ttl_seconds=_TTL_SECONDS)

    first = await provider.embed_batch(["entegrasyon testi sorgusu"])
    second = await provider.embed_batch(["entegrasyon testi sorgusu"])

    assert inner.call_count == 1
    assert first == second == [[0.1, 0.2, 0.3]]


async def test_cached_embedding_provider_uses_different_key_per_model(redis_client: Redis) -> None:
    """`.env`'de model değişirse (`name` aynı kalsa bile) eski cache
    girdileri yeni modelmiş gibi kullanılmamalı — bkz. cache.py docstring'i."""
    inner_a = _FakeEmbeddingProvider()
    inner_b = _FakeEmbeddingProvider()
    inner_b.model = f"{_MODEL}-v2"
    provider_a = CachedEmbeddingProvider(inner_a, redis_client, enabled=True, ttl_seconds=_TTL_SECONDS)
    provider_b = CachedEmbeddingProvider(inner_b, redis_client, enabled=True, ttl_seconds=_TTL_SECONDS)
    text = "aynı metin farklı model"

    await provider_a.embed_batch([text])
    await provider_b.embed_batch([text])

    assert inner_a.call_count == 1
    assert inner_b.call_count == 1


async def test_cached_llm_provider_serves_second_identical_call_from_real_redis(redis_client: Redis) -> None:
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, redis_client, enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="entegrasyon testi")]

    first = await provider.complete(messages, temperature=0.0)
    second = await provider.complete(messages, temperature=0.0)

    assert inner.call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.content == first.content
    assert second.total_tokens == 0


async def test_cached_llm_provider_never_caches_non_deterministic_temperature(redis_client: Redis) -> None:
    """`generate_recommendation()` (temperature=0.7) yanlışlıkla cache'lenip
    aynı sonuç kümesine hep birebir aynı öneri metnini dönmesin diye —
    gerçek OpenAI'a karşı elle doğrulanırken bulunan bir hatanın regresyon
    testi (bkz. backend/services/cache.py modül docstring'i)."""
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, redis_client, enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="entegrasyon testi - deterministik olmayan")]

    first = await provider.complete(messages, temperature=0.7)
    second = await provider.complete(messages, temperature=0.7)

    assert inner.call_count == 2
    assert first.from_cache is False
    assert second.from_cache is False

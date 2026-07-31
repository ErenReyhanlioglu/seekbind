"""backend/services/cache.py için birim testler."""

from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.services.cache import CachedEmbeddingProvider, CachedLLMProvider
from backend.services.llm import ChatMessage, LLMResponse

_TTL_SECONDS = 60


class _FakePipeline:
    """`_FakeRedis.pipeline()`'ın döndüğü, gerçek redis-py pipeline'ının
    burada kullanılan küçük bir alt kümesini uygulayan test double'ı."""

    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, str, int | None]] = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._ops.append((key, value, ex))

    async def execute(self) -> None:
        for key, value, ex in self._ops:
            await self._redis.set(key, value, ex=ex)


class _FakeRedis:
    """Bellek-içi, basit bir Redis taklidi — `redis.asyncio.Redis`'in
    `CachedEmbeddingProvider`/`CachedLLMProvider` tarafından kullanılan
    küçük bir alt kümesini (get/mget/set/pipeline) uygular."""

    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._fail = fail
        self.get_calls: list[str] = []
        self.mget_calls: list[list[str]] = []
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str) -> bytes | None:
        if self._fail:
            raise RedisError("bağlantı hatası")
        self.get_calls.append(key)
        value = self._store.get(key)
        return value.encode("utf-8") if value is not None else None

    async def mget(self, keys: list[str]) -> list[bytes | None]:
        if self._fail:
            raise RedisError("bağlantı hatası")
        self.mget_calls.append(list(keys))
        return [self._store[k].encode("utf-8") if k in self._store else None for k in keys]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self._fail:
            raise RedisError("bağlantı hatası")
        self.set_calls.append((key, value, ex))
        self._store[key] = value

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


class _FakeEmbeddingProvider:
    name = "openai"
    model = "text-embedding-3-small"
    dimension = 3

    def __init__(self) -> None:
        self.call_count = 0
        self.last_texts: list[str] = []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.last_texts = list(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def close(self) -> None:
        pass


class _FakeLLMProvider:
    name = "openai"
    model = "gpt-4o-mini"

    def __init__(self) -> None:
        self.call_count = 0
        self.closed = False

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
        self.closed = True


# --- CachedEmbeddingProvider ---


async def test_embed_batch_returns_empty_list_without_touching_redis_for_empty_input() -> None:
    redis = _FakeRedis()
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    result = await provider.embed_batch([])

    assert result == []
    assert inner.call_count == 0
    assert redis.mget_calls == []


async def test_embed_batch_calls_inner_on_first_call_then_serves_from_cache() -> None:
    redis = _FakeRedis()
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    first = await provider.embed_batch(["ucuz dişçi"])
    second = await provider.embed_batch(["ucuz dişçi"])

    assert inner.call_count == 1
    assert first == second == [[0.1, 0.2, 0.3]]


async def test_embed_batch_only_calls_inner_for_cache_miss_subset() -> None:
    redis = _FakeRedis()
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    await provider.embed_batch(["eski metin"])
    inner.call_count = 0  # ilk çağrının sayacını sıfırla, sadece ikinci çağrıyı ölç

    await provider.embed_batch(["eski metin", "yeni metin"])

    assert inner.call_count == 1
    assert inner.last_texts == ["yeni metin"]


async def test_embed_batch_uses_separate_cache_namespace_per_model() -> None:
    """Aynı metin, farklı `model` değerine sahip iki sağlayıcı arasında
    cache'i PAYLAŞMAMALI — .env'de model değişince eski vektörlerin
    sessizce yeni modelmiş gibi kullanılmaması için (bkz. modül docstring'i)."""
    redis = _FakeRedis()
    inner_small = _FakeEmbeddingProvider()
    inner_large = _FakeEmbeddingProvider()
    inner_large.model = "text-embedding-3-large"
    provider_small = CachedEmbeddingProvider(inner_small, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    provider_large = CachedEmbeddingProvider(inner_large, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    await provider_small.embed_batch(["aynı metin"])
    await provider_large.embed_batch(["aynı metin"])

    assert inner_small.call_count == 1
    assert inner_large.call_count == 1


async def test_embed_batch_bypasses_redis_when_disabled() -> None:
    redis = _FakeRedis()
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=False, ttl_seconds=_TTL_SECONDS)

    await provider.embed_batch(["ucuz dişçi"])
    await provider.embed_batch(["ucuz dişçi"])

    assert inner.call_count == 2
    assert redis.mget_calls == []
    assert redis.set_calls == []


async def test_embed_batch_falls_back_to_inner_when_redis_read_fails() -> None:
    redis = _FakeRedis(fail=True)
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    result = await provider.embed_batch(["ucuz dişçi"])

    assert result == [[0.1, 0.2, 0.3]]
    assert inner.call_count == 1


async def test_embed_batch_properties_delegate_to_inner() -> None:
    redis = _FakeRedis()
    inner = _FakeEmbeddingProvider()
    provider = CachedEmbeddingProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    assert provider.name == inner.name
    assert provider.model == inner.model
    assert provider.dimension == inner.dimension


# --- CachedLLMProvider ---


async def test_complete_calls_inner_on_first_call_then_serves_from_cache() -> None:
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="ucuz dişçi bul")]

    first = await provider.complete(messages, temperature=0.0)
    second = await provider.complete(messages, temperature=0.0)

    assert inner.call_count == 1
    assert first.from_cache is False
    assert first.total_tokens == 15
    assert second.from_cache is True
    assert second.content == first.content
    assert second.prompt_tokens == 0
    assert second.completion_tokens == 0
    assert second.total_tokens == 0


async def test_complete_uses_separate_cache_key_per_temperature() -> None:
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="ucuz dişçi bul")]

    await provider.complete(messages, temperature=0.0)
    await provider.complete(messages, temperature=0.7)

    assert inner.call_count == 2


async def test_complete_bypasses_redis_when_disabled() -> None:
    """`temperature=0.0` bilerek veriliyor — aksi halde bu test `enabled=False`
    yolunu değil, aşağıdaki `temperature != 0.0` bypass'ını (yanlışlıkla)
    kanıtlamış olurdu, gerçek `enabled` kontrolüne hiç dokunmadan geçerdi."""
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=False, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="ucuz dişçi bul")]

    await provider.complete(messages, temperature=0.0)
    await provider.complete(messages, temperature=0.0)

    assert inner.call_count == 2
    assert redis.get_calls == []
    assert redis.set_calls == []


async def test_complete_falls_back_to_inner_when_redis_read_fails() -> None:
    """`temperature=0.0` bilerek veriliyor — aksi halde Redis'e hiç
    dokunulmadan (temperature bypass'ı yüzünden) geçen, RedisError yolunu
    gerçekte hiç test etmeyen boş (vacuous) bir test olurdu."""
    redis = _FakeRedis(fail=True)
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="ucuz dişçi bul")]

    response = await provider.complete(messages, temperature=0.0)

    assert response.from_cache is False
    assert inner.call_count == 1


async def test_complete_bypasses_cache_for_non_deterministic_temperature() -> None:
    """`generate_recommendation()` (temperature=0.7) yanlışlıkla cache'lenip
    aynı sonuç kümesine hep birebir aynı öneri metnini dönmesin diye —
    gerçek OpenAI'a karşı elle doğrulanırken bulunan bir hatanın regresyon
    testi (bkz. cache.py modül docstring'i)."""
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="ucuz dişçi bul")]

    first = await provider.complete(messages, temperature=0.7)
    second = await provider.complete(messages, temperature=0.7)

    assert inner.call_count == 2
    assert first.from_cache is False
    assert second.from_cache is False
    assert redis.get_calls == []
    assert redis.set_calls == []


async def test_complete_properties_and_close_delegate_to_inner() -> None:
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)

    assert provider.name == inner.name
    assert provider.model == inner.model

    await provider.close()
    assert inner.closed is True


async def test_complete_never_mutates_the_original_cached_response() -> None:
    """Cache hit'te dönen `LLMResponse`, Redis'e yazılan orijinali BOZMAMALI
    — `model_copy` kullanılmazsa (elle mutasyon) sonraki okumalar da 0
    token'lı görünürdü."""
    redis = _FakeRedis()
    inner = _FakeLLMProvider()
    provider = CachedLLMProvider(inner, cast(Redis, redis), enabled=True, ttl_seconds=_TTL_SECONDS)
    messages = [ChatMessage(role="user", content="test")]

    await provider.complete(messages, temperature=0.0)
    first_hit = await provider.complete(messages, temperature=0.0)
    second_hit = await provider.complete(messages, temperature=0.0)

    assert first_hit.total_tokens == 0
    assert second_hit.total_tokens == 0
    assert inner.call_count == 1

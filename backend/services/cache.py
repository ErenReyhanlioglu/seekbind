"""Redis destekli, sağlayıcı-agnostik cache katmanı.

`CachedEmbeddingProvider`/`CachedLLMProvider`, ilgili Protocol'e (bkz.
`backend.services.embedding`, `backend.services.llm`) uyan HERHANGİ bir
sağlayıcıyı sarabilir — cache mantığı her sağlayıcı sınıfına ayrı ayrı
gömülmez, tek yerde tutulur. Bu, ileride farklı embedder/LLM kombinasyonları
denendiğinde (RAGAS ablasyonu, Faz 6) aynı cache davranışının otomatik
uygulanmasını sağlar.

Cache anahtarı her zaman sağlayıcı adı + gerçek model adını içerir (sadece
`name`'i değil) — `.env`'de model değişirse (`name` aynı kalsa bile) eski
cache girdileri sessizce yanlış modelin çıktısıymış gibi kullanılmasın diye
(Redis kalıcı, process restart'ından etkilenmez).

`CachedLLMProvider` SADECE `temperature=0.0` olan çağrıları cache'ler —
`get_llm_provider()` tek bir paylaşılan sağlayıcı döndürdüğü için (hem
intent parsing hem öneri üretimi aynı örneği kullanıyor), bu ayrım şart:
`generate_recommendation()` (`temperature=0.7`, bilerek cache dışı
bırakılmıştı — bkz. proje kararı) bu kontrol olmadan yanlışlıkla
cache'lenip aynı sonuç kümesine hep birebir aynı öneri metnini
dönerdi (gerçek OpenAI'a karşı elle doğrulanırken bulundu ve düzeltildi).
Sadece zaten deterministik olması GEREKEN çağrıları cache'lemek, cache'in
hiçbir zaman gözlemlenebilir davranışı değiştirmemesini garanti eder.

Redis'e ulaşılamazsa istek çökmez — sessizce cache miss gibi davranıp gerçek
sağlayıcıya düşülür (log ile).
"""

import hashlib
import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.services.embedding import EmbeddingProvider
from backend.services.llm import ChatMessage, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)

# CachedLLMProvider sadece bu sıcaklıktaki çağrıları cache'ler — zaten
# deterministik olması GEREKEN çağrılar (örn. intent parsing) dışındakiler
# (örn. temperature=0.7 ile üretilen öneri metni) cache'lenirse, cache'in
# "aynı girdiye her zaman aynı çıktı" garantisi, o çağrının kasıtlı
# çeşitliliğini sessizce ortadan kaldırırdı (bkz. modül docstring'i).
_DETERMINISTIC_TEMPERATURE: float = 0.0


def _hash(payload: str) -> str:
    """Deterministik özet üretir — Python'un yerleşik hash()'i PEP 456 ile
    süreç başına tuzlandığı için kalıcı bir cache anahtarı olarak kullanılamaz."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CachedEmbeddingProvider:
    """`EmbeddingProvider` Protocol'üne uyar, gerçek sağlayıcıyı Redis cache ile sarar."""

    def __init__(
        self,
        inner: EmbeddingProvider,
        redis_client: Redis,
        *,
        enabled: bool,
        ttl_seconds: int,
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    def _cache_key(self, text: str) -> str:
        return f"embed:{self._inner.name}:{self._inner.model}:{_hash(text)}"

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Her metni ayrı ayrı cache'ler — sadece cache'de olmayanlar için
        gerçek sağlayıcıya tek bir toplu (batch) istek atılır."""
        if not texts:
            return []
        if not self._enabled:
            return await self._inner.embed_batch(texts)

        keys = [self._cache_key(text) for text in texts]
        try:
            cached_values = await self._redis.mget(keys)
        except RedisError as e:
            logger.warning("Redis'ten embedding okunamadı, cache atlanıyor: %s", e)
            return await self._inner.embed_batch(texts)

        results: list[list[float] | None] = [
            json.loads(value) if value is not None else None for value in cached_values
        ]
        miss_indices = [i for i, vector in enumerate(results) if vector is None]

        if miss_indices:
            miss_texts = [texts[i] for i in miss_indices]
            fresh_vectors = await self._inner.embed_batch(miss_texts)
            for index, vector in zip(miss_indices, fresh_vectors):
                results[index] = vector
            try:
                async with self._redis.pipeline() as pipe:
                    for index in miss_indices:
                        pipe.set(
                            keys[index],
                            json.dumps(results[index]),
                            ex=self._ttl_seconds,
                        )
                    await pipe.execute()
            except RedisError as e:
                logger.warning(
                    "Redis'e embedding yazılamadı, sonuç yine de dönülüyor: %s", e
                )

        return [vector for vector in results if vector is not None]

    async def close(self) -> None:
        await self._inner.close()


class CachedLLMProvider:
    """`LLMProvider` Protocol'üne uyar, gerçek sağlayıcıyı Redis cache ile sarar."""

    def __init__(
        self,
        inner: LLMProvider,
        redis_client: Redis,
        *,
        enabled: bool,
        ttl_seconds: int,
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def model(self) -> str:
        return self._inner.model

    def _cache_key(
        self,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
    ) -> str:
        # langfuse_name/langfuse_metadata bilerek dışarıda bırakıldı — gerçek
        # tamamlama içeriğini etkilemiyorlar, sadece izleme amaçlı.
        payload = json.dumps(
            {
                "messages": [m.model_dump() for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": response_format,
            },
            sort_keys=True,
        )
        return f"llm:{self._inner.name}:{self._inner.model}:{_hash(payload)}"

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
        if not self._enabled or temperature != _DETERMINISTIC_TEMPERATURE:
            return await self._inner.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                langfuse_name=langfuse_name,
                langfuse_metadata=langfuse_metadata,
            )

        key = self._cache_key(messages, temperature, max_tokens, response_format)
        try:
            cached = await self._redis.get(key)
        except RedisError as e:
            logger.warning("Redis'ten LLM cevabı okunamadı, cache atlanıyor: %s", e)
            cached = None

        if cached is not None:
            # Gerçek bir çağrı olmadığı için token sayıları 0'a çekilir —
            # Langfuse/maliyet takibinin cache hit'i gerçek harcama gibi
            # göstermemesi için (bkz. modül docstring'i).
            original = LLMResponse.model_validate_json(cached)
            return original.model_copy(
                update={
                    "from_cache": True,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }
            )

        response = await self._inner.complete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            langfuse_name=langfuse_name,
            langfuse_metadata=langfuse_metadata,
        )
        try:
            await self._redis.set(key, response.model_dump_json(), ex=self._ttl_seconds)
        except RedisError as e:
            logger.warning(
                "Redis'e LLM cevabı yazılamadı, cevap yine de dönülüyor: %s", e
            )
        return response

    async def close(self) -> None:
        await self._inner.close()

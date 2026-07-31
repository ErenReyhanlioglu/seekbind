"""Embedding sağlayıcıları.

Birden fazla sağlayıcı (OpenAI, ileride Ollama/Türkçe özel modeller)
arasında geçiş kod değişikliği değil config değişikliği olsun diye
Protocol ile soyutlanmıştır.
"""

from functools import lru_cache
from typing import Protocol

from openai import APIError, APITimeoutError, AsyncOpenAI

from backend.config import get_settings
from backend.db.redis import get_redis_client


class EmbeddingServiceError(Exception):
    """Embedding üretimi başarısız olduğunda fırlatılır."""


class EmbeddingProvider(Protocol):
    """Embedding sağlayıcıları için ortak arayüz."""

    @property
    def name(self) -> str:
        """Qdrant collection adında kullanılan kısa sağlayıcı adı (örn. 'openai')."""
        ...

    @property
    def model(self) -> str:
        """Kullanılan gerçek model adı (örn. 'text-embedding-3-small').

        `name`'den ayrı tutulur: `name` Qdrant collection adı için sabit bir
        sağlayıcı kimliği, `model` ise cache anahtarının doğruluğu için gerekli
        (bkz. `backend.services.cache`) — `.env`'de model değişirse `name` aynı
        kalır ama `model` değişir, cache key'i de otomatik değişmeli.
        """
        ...

    @property
    def dimension(self) -> int:
        """Üretilen vektörlerin boyutu."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Birden fazla metni tek istekte embed eder."""
        ...


class OpenAIEmbedding:
    """OpenAI embedding modeliyle (config'teki OPENAI_EMBEDDING_MODEL) embedding üretimi."""

    _DIMENSION: int = 1536  # text-embedding-3-small

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._model = settings.openai_embedding_model
        self._timeout_seconds = settings.llm_call_timeout_seconds

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """OpenAI'den birden fazla metnin embedding'ini tek istekte alır."""
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                timeout=self._timeout_seconds,
            )
        except APITimeoutError as e:
            raise EmbeddingServiceError("OpenAI embedding isteği zaman aşımına uğradı") from e
        except APIError as e:
            raise EmbeddingServiceError(f"OpenAI embedding API hatası: {e}") from e
        return [item.embedding for item in response.data]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Kullanılacak embedding sağlayıcısını (Redis cache ile sarılmış olarak)
    önbellekten döner.

    Gerçek sağlayıcı seçimi şimdilik tek (OpenAI); birden fazla sağlayıcı
    eklenince burada config'e göre seçim yapılacak.

    `CachedEmbeddingProvider` import'u bilerek fonksiyon içinde (modül
    seviyesinde değil) — `cache.py` çalışma zamanında `llm.py`'den
    `ChatMessage`/`LLMResponse`'a ihtiyaç duyuyor, bu da `embedding.py` ↔
    `cache.py` arasında modül-seviyesinde bir devridaim (circular import)
    yaratırdı. Fonksiyon çağrılana kadar erteleyince (bu modül tamamen
    yüklendikten sonra) sorun ortadan kalkıyor — Python'da bu tür
    "wiring" fonksiyonları için standart, kabul edilmiş bir çözüm.
    """
    from backend.services.cache import CachedEmbeddingProvider

    settings = get_settings()
    inner = OpenAIEmbedding()
    return CachedEmbeddingProvider(
        inner,
        get_redis_client(),
        enabled=settings.enable_cache,
        ttl_seconds=settings.embedding_cache_ttl_seconds,
    )


QDRANT_COLLECTION_PREFIX: str = "businesses"


def get_qdrant_collection_name(provider: EmbeddingProvider) -> str:
    """Sağlayıcıya göre Qdrant collection adını üretir (örn. 'businesses_openai').

    load_embeddings.py ve arama tarafı (search.py) aynı collection'ı aynı
    isimlendirme kuralıyla bulsun diye tek yerden üretilir.
    """
    return f"{QDRANT_COLLECTION_PREFIX}_{provider.name}"

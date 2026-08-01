"""Embedding sağlayıcıları.

Birden fazla sağlayıcı (OpenAI, Ollama üzerinden Qwen3) arasında geçiş kod
değişikliği değil config değişikliği olsun diye Protocol ile soyutlanmıştır.

Sağlayıcılar arası otomatik fallback (OpenAI hata verirse Ollama'ya geçme)
`backend.services.fallback.FallbackEmbeddingProvider` içinde, bu modülün
dışında yaşar (bkz. `get_embedding_provider`).
"""

import re
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

    async def close(self) -> None:
        """Açık HTTP bağlantılarını kapatır (graceful shutdown için)."""
        ...


async def _run_embedding(
    client: AsyncOpenAI,
    model: str,
    provider_name: str,
    texts: list[str],
    timeout_seconds: int,
) -> list[list[float]]:
    """İki sağlayıcının da (OpenAI/Ollama) paylaştığı istek/hata-eşleme mantığı.

    `backend.services.llm._run_completion()` ile aynı desen.
    """
    try:
        response = await client.embeddings.create(
            model=model, input=texts, timeout=timeout_seconds
        )
    except APITimeoutError as e:
        raise EmbeddingServiceError(
            f"{provider_name} embedding isteği zaman aşımına uğradı"
        ) from e
    except APIError as e:
        raise EmbeddingServiceError(f"{provider_name} embedding API hatası: {e}") from e
    return [item.embedding for item in response.data]


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
        return await _run_embedding(
            self._client, self._model, self.name, texts, self._timeout_seconds
        )

    async def close(self) -> None:
        await self._client.close()


_OLLAMA_DUMMY_API_KEY: str = (
    "ollama"  # Ollama'nın OpenAI-uyumlu endpoint'i doğrulamıyor, dolu bir string yeterli
)
_MODEL_TAG_SANITIZE_PATTERN: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def _sanitize_model_tag(model: str) -> str:
    """Model adını Qdrant collection adında güvenle kullanılabilecek bir parçaya çevirir.

    `qwen3-embedding:0.6b` -> `qwen3-embedding-0-6b`. Her Ollama-tabanlı
    embedding modelinin `.name`'i buradan türer (bkz. `OllamaEmbedding.name`)
    — modele özgü olduğu için, farklı boyuttaki iki Ollama modeli asla aynı
    Qdrant collection adını üretemez (bkz. modül docstring'i, ADR-0024).
    """
    return _MODEL_TAG_SANITIZE_PATTERN.sub("-", model.lower()).strip("-")


# Ollama, OpenAI'nin aksine embedding boyutunu API yanıtından (senkron,
# çağrı öncesi) öğrenmenin bir yolunu vermiyor — bu yüzden bilinen her
# Ollama-tabanlı embedding modelinin gerçek boyutu burada elle sabitlenir.
# Yanlış boyutla bir Qdrant collection'ı oluşturmak sessiz değil (Qdrant
# upsert'i reddeder), ama HANGİ boyutun doğru olduğunu bilmeden devam etmek
# yerine tanınmayan bir model için açıkça fail-fast olmak tercih edildi
# (bkz. `OllamaEmbedding.__init__`, docs/adr/0024).
_OLLAMA_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "qwen3-embedding:0.6b": 1024,  # ADR-0023 — canlı fallback hedefi
    "alibayram/embeddingmagibu-200m": 768,  # ADR-0023 — sadece RAGAS ablasyonu, canlı hedef değil
}


class OllamaEmbedding:
    """Ollama'nın OpenAI-uyumlu /v1 endpoint'iyle (config'teki OLLAMA_EMBEDDING_MODEL
    — ADR-0023: qwen3-embedding:0.6b) embedding üretimi.

    `OllamaLLM` (bkz. `backend.services.llm`) ile aynı desen — ayrı bir
    `ollama` paketi gerekmiyor, aynı OpenAI client sınıfı yeniden kullanılıyor.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.ollama_embedding_model
        if self._model not in _OLLAMA_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Bilinmeyen OLLAMA_EMBEDDING_MODEL: '{self._model}' — gerçek boyutu "
                f"_OLLAMA_EMBEDDING_DIMENSIONS'a eklenmeden kullanılamaz (yanlış boyutla "
                f"Qdrant collection'ı oluşturmak sessiz veri bozulmasına yol açar)."
            )
        self._dimension = _OLLAMA_EMBEDDING_DIMENSIONS[self._model]
        self._client = AsyncOpenAI(
            api_key=_OLLAMA_DUMMY_API_KEY,
            base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
        )
        self._timeout_seconds = settings.llm_call_timeout_seconds

    @property
    def name(self) -> str:
        return f"ollama-{_sanitize_model_tag(self._model)}"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await _run_embedding(
            self._client, self._model, self.name, texts, self._timeout_seconds
        )

    async def close(self) -> None:
        await self._client.close()


@lru_cache
def get_embedding_provider(*, allow_fallback: bool = True) -> EmbeddingProvider:
    """Kullanılacak embedding sağlayıcısını (Redis cache + fallback ile
    sarılmış olarak) önbellekten döner.

    Birincil her zaman OpenAI, ikincil her zaman Ollama (bkz.
    `backend.services.fallback.FallbackEmbeddingProvider`) —
    `ACTIVE_LLM_PROVIDER`'ın aksine embedding tarafında "tamamen yerel çalış"
    diye ayrı bir seçim yok (bkz. ADR-0023), OpenAI hep birincil.

    `allow_fallback=False`, toplu yükleme gibi (bkz. `scripts.load_embeddings`)
    senaryolarda fallback'i tamamen devre dışı bırakır — OpenAI geçici olarak
    ulaşılamazken bir kısım vektörün sessizce Ollama'nın farklı anlamsal
    uzayından aynı collection'a yazılması, testle yakalanamayan kalıcı bir
    veri bozulması olurdu; bu durumda istek fail-fast başarısız olmalı.
    `@lru_cache` her `allow_fallback` değeri için ayrı bir örnek ürettiğinden
    (fonksiyon farklı argümanla iki kez çağrılmış sayılır), bu iki yol
    birbirine karışmaz.

    `CachedEmbeddingProvider`/`FallbackEmbeddingProvider` import'ları bilerek
    fonksiyon içinde (modül seviyesinde değil) — `cache.py`/`fallback.py`
    çalışma zamanında bu modüle ihtiyaç duyuyor, modül-seviyesinde bir
    devridaim (circular import) yaratırdı. Fonksiyon çağrılana kadar
    erteleyince (bu modül tamamen yüklendikten sonra) sorun ortadan kalkıyor
    — Python'da bu tür "wiring" fonksiyonları için standart, kabul edilmiş
    bir çözüm.
    """
    from backend.services.cache import CachedEmbeddingProvider

    settings = get_settings()
    redis_client = get_redis_client()
    cache_kwargs = {
        "enabled": settings.enable_cache,
        "ttl_seconds": settings.embedding_cache_ttl_seconds,
    }

    primary = CachedEmbeddingProvider(OpenAIEmbedding(), redis_client, **cache_kwargs)
    if not allow_fallback:
        return primary

    from backend.services.fallback import FallbackEmbeddingProvider

    secondary = CachedEmbeddingProvider(OllamaEmbedding(), redis_client, **cache_kwargs)
    return FallbackEmbeddingProvider(
        primary, secondary, enabled=settings.enable_fallback
    )


QDRANT_COLLECTION_PREFIX: str = "businesses"


def get_qdrant_collection_name(provider: EmbeddingProvider) -> str:
    """Sağlayıcıya göre Qdrant collection adını üretir (örn. 'businesses_openai').

    load_embeddings.py ve arama tarafı (search.py) aynı collection'ı aynı
    isimlendirme kuralıyla bulsun diye tek yerden üretilir.
    """
    return f"{QDRANT_COLLECTION_PREFIX}_{provider.name}"

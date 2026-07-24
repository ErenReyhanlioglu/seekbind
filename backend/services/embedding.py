"""Embedding sağlayıcıları.

Birden fazla sağlayıcı (OpenAI, ileride Ollama/Türkçe özel modeller)
arasında geçiş kod değişikliği değil config değişikliği olsun diye
Protocol ile soyutlanmıştır.
"""

from functools import lru_cache
from typing import Protocol

from openai import APIError, APITimeoutError, AsyncOpenAI

from backend.config import get_settings


class EmbeddingServiceError(Exception):
    """Embedding üretimi başarısız olduğunda fırlatılır."""


class EmbeddingProvider(Protocol):
    """Embedding sağlayıcıları için ortak arayüz."""

    @property
    def name(self) -> str:
        """Qdrant collection adında kullanılan kısa sağlayıcı adı (örn. 'openai')."""
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
    """Kullanılacak embedding sağlayıcısını önbellekten döner.

    Şimdilik tek sağlayıcı (OpenAI) var; birden fazla sağlayıcı
    eklenince burada config'e göre seçim yapılacak.
    """
    return OpenAIEmbedding()

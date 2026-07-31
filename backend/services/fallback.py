"""Sağlayıcılar arası otomatik fallback (OpenAI birincil, Ollama ikincil).

`FallbackLLMProvider`/`FallbackEmbeddingProvider`, ilgili Protocol'e (bkz.
`backend.services.llm`, `backend.services.embedding`) uyan bir birincil +
ikincil sağlayıcı çiftini sarar — birincil başarısız olursa ikincil denenir.
Yön her zaman sabit: birincil=OpenAI, ikincil=Ollama (bkz. docs/roadmap.md
`feature/fallback-mechanism`) — ters yönlü fallback (Ollama birincilken
OpenAI'a düşme) kapsam dışı, `ACTIVE_LLM_PROVIDER=ollama` iken bu sınıflar
hiç kullanılmaz (bkz. `get_llm_provider`/`get_embedding_provider`).

LLM ve embedding fallback'i simetrik DEĞİL. Bir LLM cevabının Ollama'dan
gelmesi başka hiçbir şeyi etkilemez — ama bir embedding'in Ollama'dan gelmesi,
farklı (kıyaslanamaz) bir vektör uzayında, farklı boyutta bir sonuç demektir
(bkz. `backend.services.embedding.get_qdrant_collection_name`). Bu yüzden
`FallbackEmbeddingProvider`, o anki asyncio task'ında EN SON hangi
sağlayıcının gerçekten kullanıldığını bir `contextvars.ContextVar` ile takip
eder (Langfuse'un `@observe()`/`langfuse_context` mekanizmasıyla aynı desen,
bkz. `backend.services.rag.service` docstring'i) — `get_embedding_provider()`
`@lru_cache`'li tek bir paylaşılan örnek döndürdüğü için, düz bir instance
attribute eşzamanlı isteklerde yarış durumuna (race condition) girip yanlış
isteğin yanlış Qdrant collection'ına gitmesine yol açardı.
"""

import contextvars
import logging

from backend.services.embedding import EmbeddingProvider, EmbeddingServiceError
from backend.services.llm import ChatMessage, LLMProvider, LLMResponse, LLMServiceError

logger = logging.getLogger(__name__)


class FallbackLLMProvider:
    """`LLMProvider` Protocol'üne uyar; birincil başarısız olursa ikincile düşer.

    `.name`/`.model` her zaman birincili yansıtır — LLM cevabının hangi
    sağlayıcıdan geldiği, embedding'in aksine, sonraki hiçbir çağrıyı
    (örn. bir collection seçimini) etkilemediği için bunun dinamik olmasına
    gerek yok.
    """

    def __init__(self, primary: LLMProvider, secondary: LLMProvider, *, enabled: bool) -> None:
        self._primary = primary
        self._secondary = secondary
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._primary.name

    @property
    def model(self) -> str:
        return self._primary.model

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
        if not self._enabled:
            return await self._primary.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                langfuse_name=langfuse_name,
                langfuse_metadata=langfuse_metadata,
            )
        try:
            return await self._primary.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                langfuse_name=langfuse_name,
                langfuse_metadata=langfuse_metadata,
            )
        except LLMServiceError as e:
            logger.warning(
                "Birincil LLM (%s) başarısız, ikincile (%s) düşülüyor: %s",
                self._primary.name,
                self._secondary.name,
                e,
            )
            return await self._secondary.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                langfuse_name=langfuse_name,
                langfuse_metadata=langfuse_metadata,
            )

    async def close(self) -> None:
        await self._primary.close()
        await self._secondary.close()


# İkincil sağlayıcı gerçekten kullanıldığında, o anki asyncio task'ı için
# EmbeddingProvider kimliğini (name, model, dimension) taşır — bkz. modül
# docstring'i. Varsayılan None: henüz hiç embed_batch() çağrılmamış demek,
# bu durumda .name/.model/.dimension birincile düşer.
_active_embedding_identity: contextvars.ContextVar[tuple[str, str, int] | None] = contextvars.ContextVar(
    "fallback_embedding_active_identity", default=None
)


class FallbackEmbeddingProvider:
    """`EmbeddingProvider` Protocol'üne uyar; birincil başarısız olursa ikincile düşer.

    `.name`/`.model`/`.dimension`, o anki task'ta en son `embed_batch()`'i
    gerçekten hangi sağlayıcının servis ettiğini yansıtır (bkz. modül
    docstring'i) — `get_qdrant_collection_name()` bu değere göre doğru
    collection'ı seçebilsin diye.
    """

    def __init__(self, primary: EmbeddingProvider, secondary: EmbeddingProvider, *, enabled: bool) -> None:
        self._primary = primary
        self._secondary = secondary
        self._enabled = enabled

    @staticmethod
    def _identity(provider: EmbeddingProvider) -> tuple[str, str, int]:
        return (provider.name, provider.model, provider.dimension)

    @property
    def name(self) -> str:
        identity = _active_embedding_identity.get()
        return identity[0] if identity is not None else self._primary.name

    @property
    def model(self) -> str:
        identity = _active_embedding_identity.get()
        return identity[1] if identity is not None else self._primary.model

    @property
    def dimension(self) -> int:
        identity = _active_embedding_identity.get()
        return identity[2] if identity is not None else self._primary.dimension

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._enabled:
            return await self._primary.embed_batch(texts)
        try:
            result = await self._primary.embed_batch(texts)
            _active_embedding_identity.set(self._identity(self._primary))
            return result
        except EmbeddingServiceError as e:
            logger.warning(
                "Birincil embedding (%s) başarısız, ikincile (%s) düşülüyor: %s",
                self._primary.name,
                self._secondary.name,
                e,
            )
            result = await self._secondary.embed_batch(texts)
            _active_embedding_identity.set(self._identity(self._secondary))
            return result

    async def close(self) -> None:
        await self._primary.close()
        await self._secondary.close()

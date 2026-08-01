"""LLM sağlayıcıları.

Birden fazla sağlayıcı (OpenAI, Ollama üzerinden Qwen3/Turkish-LLM) arasında
geçiş kod değişikliği değil config değişikliği olsun diye Protocol ile
soyutlanmıştır (bkz. `backend.services.embedding`'deki aynı desen).

Bu modül prompt-agnostiktir — hangi sistem promptunun kullanılacağına ya da
prompt injection kontrolüne karar vermez, sadece mesaj listesi alıp
tamamlama üretir. Bu kararlar `feature/rag-pipeline`'ın kapsamındadır.

Sağlayıcılar arası otomatik fallback (OpenAI hata verirse Ollama'ya geçme)
`backend.services.fallback.FallbackLLMProvider` içinde, bu modülün dışında
yaşar (bkz. `get_llm_provider`) — çağıranlar (routes.py, rag/service.py)
fallback'in var olduğunu hiç bilmez, Protocol arayüzü değişmez.
"""

import asyncio
from functools import lru_cache
from typing import Literal, Protocol

# langfuse paketi AsyncOpenAI'ı __all__ ile dışa vurmuyor, Pyright bu yüzden
# "private import" sanıyor — ama bu, langfuse'un dokümante ettiği asıl
# kullanım şekli (openai.AsyncOpenAI yerine bunu kullanınca her çağrı
# otomatik izlenir), gerçek bir hata değil.
from langfuse.openai import AsyncOpenAI  # pyright: ignore[reportPrivateImportUsage]
from openai import APIConnectionError, APIError, APITimeoutError
from pydantic import BaseModel

from backend.config import get_settings
from backend.core.monitoring import get_langfuse_client
from backend.db.redis import get_redis_client


class LLMServiceError(Exception):
    """LLM completion isteği başarısız olduğunda fırlatılır."""


class ChatMessage(BaseModel):
    """Bir completion isteğindeki tek bir mesaj (system/user/assistant)."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    """Bir completion çağrısının sonucu.

    Token sayıları dahil edilir — düz bir `str` yeterli değil: Langfuse
    maliyet görünürlüğü ve ileride RAGAS'ın aday karşılaştırması için gerekli.
    """

    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    finish_reason: str | None
    # Gerçek sağlayıcılar (OpenAILLM/OllamaLLM) her zaman False döner;
    # CachedLLMProvider cache hit'te True set eder — Langfuse'ta gerçek
    # olmayan bir çağrının token sayısı harcama gibi görünmesin diye
    # (bkz. backend.services.cache), cache hit'te token sayıları 0'a çekilir.
    from_cache: bool = False


class LLMProvider(Protocol):
    """LLM sağlayıcıları için ortak arayüz."""

    @property
    def name(self) -> str:
        """Kısa sağlayıcı adı (örn. 'openai', 'ollama')."""
        ...

    @property
    def model(self) -> str:
        """Kullanılan gerçek model adı (örn. 'gpt-4o-mini', 'qwen3:7b').

        `name`'den ayrı: cache anahtarının doğruluğu için gerekli (bkz.
        `backend.services.cache`, `backend.services.embedding.EmbeddingProvider.model`
        ile aynı gerekçe).
        """
        ...

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
        """Verilen mesaj listesinden bir tamamlama üretir.

        `response_format={"type": "json_object"}` verilirse çıktı geçerli
        JSON olmaya zorlanır (bkz. intent parsing, `backend.services.rag`).

        `langfuse_name`/`langfuse_metadata`, `feature/langfuse-integration`
        kapsamında eklendi — bu adımın Langfuse'ta hangi isimle ve hangi
        ek bilgiyle görüneceğini belirler. `langfuse.openai.AsyncOpenAI`
        sarmalayıcısı bunları gerçek API'ye göndermeden önce kendi
        tarafında tüketir (`OpenAiArgsExtractor`) — provider-agnostic,
        Ollama'nın OpenAI-uyumlu endpoint'ine hiç ulaşmaz.
        """
        ...

    async def close(self) -> None:
        """Açık HTTP bağlantılarını kapatır (graceful shutdown için)."""
        ...


async def _run_completion(
    client: AsyncOpenAI,
    model: str,
    provider_name: str,
    messages: list[ChatMessage],
    temperature: float,
    max_tokens: int | None,
    response_format: dict[str, str] | None,
    timeout_seconds: int,
    langfuse_name: str | None,
    langfuse_metadata: dict[str, object] | None,
) -> LLMResponse:
    """İki sağlayıcının da paylaştığı istek/hata-eşleme mantığı."""
    payload = [{"role": m.role, "content": m.content} for m in messages]
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=payload,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,  # type: ignore[arg-type]
            timeout=timeout_seconds,
            name=langfuse_name,
            metadata=langfuse_metadata,
        )
    # Sıralama önemli: APITimeoutError, APIConnectionError'ın; o da
    # APIError'ın alt sınıfı. Yanlış sırada olsa en spesifik durumlar hiç
    # yakalanmaz, hepsi genel APIError mesajına düşerdi.
    except APITimeoutError as e:
        raise LLMServiceError(f"{provider_name} LLM isteği zaman aşımına uğradı") from e
    except APIConnectionError as e:
        raise LLMServiceError(f"{provider_name} LLM'e bağlanılamadı") from e
    except APIError as e:
        raise LLMServiceError(f"{provider_name} LLM API hatası: {e}") from e

    choice = response.choices[0]
    usage = response.usage
    return LLMResponse(
        content=choice.message.content or "",
        model=response.model,
        provider=provider_name,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
        finish_reason=choice.finish_reason,
    )


class OpenAILLM:
    """OpenAI'nin chat completion API'siyle (config'teki OPENAI_LLM_MODEL,
    ADR-0008: gpt-4o-mini) tamamlama üretimi."""

    def __init__(self) -> None:
        settings = get_settings()
        get_langfuse_client()  # Langfuse client kurulmadan izleme aktif olmaz
        self._client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self._model = settings.openai_llm_model
        self._timeout_seconds = settings.llm_call_timeout_seconds
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrent_calls)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

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
        async with self._semaphore:
            return await _run_completion(
                self._client,
                self._model,
                self.name,
                messages,
                temperature,
                max_tokens,
                response_format,
                self._timeout_seconds,
                langfuse_name,
                langfuse_metadata,
            )

    async def close(self) -> None:
        await self._client.close()


_OLLAMA_DUMMY_API_KEY: str = (
    "ollama"  # Ollama'nın OpenAI-uyumlu endpoint'i doğrulamıyor, dolu bir string yeterli
)


class OllamaLLM:
    """Ollama'nın OpenAI-uyumlu /v1 endpoint'iyle (config'teki OLLAMA_LLM_MODEL
    — ADR-0023/ADR-0024: qwen3:4b-instruct-2507-q4_K_M, fallback hedefi) tamamlama üretimi.

    Ayrı bir `ollama` paketi gerekmiyor — `embedding.py`'deki gibi aynı
    OpenAI client sınıfı yeniden kullanılıyor, sadece base_url farklı.
    """

    def __init__(self) -> None:
        settings = get_settings()
        get_langfuse_client()
        self._client = AsyncOpenAI(
            api_key=_OLLAMA_DUMMY_API_KEY,
            base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
        )
        self._model = settings.ollama_llm_model
        self._timeout_seconds = settings.llm_call_timeout_seconds
        self._semaphore = asyncio.Semaphore(settings.llm_max_concurrent_calls)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

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
        async with self._semaphore:
            return await _run_completion(
                self._client,
                self._model,
                self.name,
                messages,
                temperature,
                max_tokens,
                response_format,
                self._timeout_seconds,
                langfuse_name,
                langfuse_metadata,
            )

    async def close(self) -> None:
        await self._client.close()


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Config'teki ACTIVE_LLM_PROVIDER'a göre kullanılacak LLM sağlayıcısını
    (Redis cache + fallback ile sarılmış olarak) döner.

    `ACTIVE_LLM_PROVIDER=ollama` iken fallback hiç kurulmaz — roadmap'in
    yönü hep birincil(openai)->ikincil(ollama); tersi, "sadece yerel çalış"
    diye bilinçli seçim yapan birine sessizce OpenAI trafiği/maliyeti
    bindirir, bu niyeti ihlal eder (bkz. `backend.services.fallback`).

    `CachedLLMProvider`/`FallbackLLMProvider` import'ları bilerek fonksiyon
    içinde — `cache.py`/`fallback.py` bu modülden `ChatMessage`/`LLMResponse`'ı
    çalışma zamanında kullanıyor, bu modülün factory'si de onlara ihtiyaç
    duyunca modül-seviyesinde bir devridaim (circular import) oluşurdu.
    Fonksiyon çağrılana kadar erteleyince (bu modül tamamen yüklendikten
    sonra) sorun ortadan kalkıyor.
    """
    from backend.services.cache import CachedLLMProvider

    settings = get_settings()
    redis_client = get_redis_client()
    cache_kwargs = {
        "enabled": settings.enable_cache,
        "ttl_seconds": settings.llm_cache_ttl_seconds,
    }

    if settings.active_llm_provider == "ollama":
        return CachedLLMProvider(OllamaLLM(), redis_client, **cache_kwargs)

    from backend.services.fallback import FallbackLLMProvider

    primary = CachedLLMProvider(OpenAILLM(), redis_client, **cache_kwargs)
    secondary = CachedLLMProvider(OllamaLLM(), redis_client, **cache_kwargs)
    return FallbackLLMProvider(primary, secondary, enabled=settings.enable_fallback)

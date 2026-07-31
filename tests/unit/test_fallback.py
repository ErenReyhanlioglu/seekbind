"""backend/services/fallback.py için birim testler."""

import asyncio

from backend.services.embedding import EmbeddingServiceError
from backend.services.fallback import FallbackEmbeddingProvider, FallbackLLMProvider
from backend.services.llm import ChatMessage, LLMResponse, LLMServiceError

_MESSAGES: list[ChatMessage] = [ChatMessage(role="user", content="selam")]


class _FakeLLMProvider:
    """`LLMProvider` Protocol'üne uyan, isteğe bağlı hata enjekte edebilen test double'ı."""

    def __init__(self, name: str, model: str, *, fail: bool = False, raise_other: bool = False) -> None:
        self.name = name
        self.model = model
        self._fail = fail
        self._raise_other = raise_other
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
        if self._raise_other:
            raise ValueError("beklenmeyen, LLM'e özgü olmayan bir hata")
        if self._fail:
            raise LLMServiceError(f"{self.name} başarısız")
        return LLMResponse(
            content=f"{self.name} cevabı",
            model=self.model,
            provider=self.name,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            finish_reason="stop",
        )

    async def close(self) -> None:
        self.closed = True


class _FakeEmbeddingProvider:
    """`EmbeddingProvider` Protocol'üne uyan test double'ı.

    `fail_trigger` verilirse, SADECE o metni içeren `embed_batch()` çağrıları
    başarısız olur — bu, tek bir örneğin bazı çağrılarda başarılı bazılarında
    başarısız davranmasını gerektiren eşzamanlılık testinde kullanılıyor
    (bkz. `test_concurrent_tasks_do_not_leak_identity_across_each_other`).
    """

    def __init__(
        self,
        name: str,
        model: str,
        dimension: int = 3,
        *,
        fail: bool = False,
        fail_trigger: str | None = None,
        raise_other: bool = False,
        yield_before_return: bool = False,
    ) -> None:
        self.name = name
        self.model = model
        self.dimension = dimension
        self._fail = fail
        self._fail_trigger = fail_trigger
        self._raise_other = raise_other
        self._yield_before_return = yield_before_return
        self.call_count = 0
        self.closed = False

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        if self._yield_before_return:
            # Gerçek bir HTTP çağrısını taklit eder — event loop'un başka bir
            # task'a geçebilmesi için kasıtlı bir askıya alma noktası (bkz.
            # eşzamanlılık testi, aksi halde iki task hiç iç içe geçmeden
            # sırayla çalışabilir, bu da testi anlamsızca hep "geçer" yapardı).
            await asyncio.sleep(0)
        if self._raise_other:
            raise ValueError("beklenmeyen, embedding'e özgü olmayan bir hata")
        if self._fail or (self._fail_trigger is not None and self._fail_trigger in texts):
            raise EmbeddingServiceError(f"{self.name} başarısız")
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def close(self) -> None:
        self.closed = True


# --- FallbackLLMProvider ---


async def test_complete_returns_primary_response_without_calling_secondary_when_primary_succeeds() -> None:
    primary = _FakeLLMProvider("openai", "gpt-4o-mini")
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    response = await provider.complete(_MESSAGES)

    assert response.provider == "openai"
    assert primary.call_count == 1
    assert secondary.call_count == 0


async def test_complete_falls_back_to_secondary_when_primary_raises_llm_service_error() -> None:
    primary = _FakeLLMProvider("openai", "gpt-4o-mini", fail=True)
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    response = await provider.complete(_MESSAGES)

    assert response.provider == "ollama"
    assert primary.call_count == 1
    assert secondary.call_count == 1


async def test_complete_raises_llm_service_error_when_both_primary_and_secondary_fail() -> None:
    """İkisi de başarısız olursa dışarı sızan hâlâ düz bir LLMServiceError olmalı
    — rag/intent.py ve rag/recommendation.py'nin bunu zaten yakalayan mevcut
    `except LLMServiceError` blokları bu sayede hiç değişmeden çalışmaya devam eder."""
    primary = _FakeLLMProvider("openai", "gpt-4o-mini", fail=True)
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507", fail=True)
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    try:
        await provider.complete(_MESSAGES)
        assert False, "LLMServiceError bekleniyordu"
    except LLMServiceError:
        pass


async def test_complete_does_not_fallback_for_non_llm_service_error() -> None:
    """Yakalama sadece LLMServiceError'a özgü olmalı — başka bir exception tipi
    secondary'yi tetiklemeden olduğu gibi dışarı sızmalı."""
    primary = _FakeLLMProvider("openai", "gpt-4o-mini", raise_other=True)
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    try:
        await provider.complete(_MESSAGES)
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass
    assert secondary.call_count == 0


async def test_complete_skips_fallback_when_disabled() -> None:
    primary = _FakeLLMProvider("openai", "gpt-4o-mini", fail=True)
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=False)

    try:
        await provider.complete(_MESSAGES)
        assert False, "LLMServiceError bekleniyordu"
    except LLMServiceError:
        pass
    assert secondary.call_count == 0


def test_llm_name_and_model_reflect_primary() -> None:
    primary = _FakeLLMProvider("openai", "gpt-4o-mini")
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    assert provider.name == "openai"
    assert provider.model == "gpt-4o-mini"


async def test_llm_close_closes_both_providers() -> None:
    primary = _FakeLLMProvider("openai", "gpt-4o-mini")
    secondary = _FakeLLMProvider("ollama", "qwen3:4b-instruct-2507")
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    await provider.close()

    assert primary.closed
    assert secondary.closed


# --- FallbackEmbeddingProvider ---


async def test_embed_batch_returns_primary_result_without_calling_secondary_when_primary_succeeds() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small")
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", dimension=1024)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    result = await provider.embed_batch(["metin"])

    assert result == [[0.1, 0.2, 0.3]]
    assert primary.call_count == 1
    assert secondary.call_count == 0


async def test_embed_batch_falls_back_to_secondary_when_primary_raises_embedding_service_error() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small", fail=True)
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", dimension=1024)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    result = await provider.embed_batch(["metin"])

    assert result == [[0.1, 0.2, 0.3]]
    assert primary.call_count == 1
    assert secondary.call_count == 1


async def test_embed_batch_raises_embedding_service_error_when_both_fail() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small", fail=True)
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", fail=True)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    try:
        await provider.embed_batch(["metin"])
        assert False, "EmbeddingServiceError bekleniyordu"
    except EmbeddingServiceError:
        pass


async def test_embed_batch_does_not_fallback_for_non_embedding_service_error() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small", raise_other=True)
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b")
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    try:
        await provider.embed_batch(["metin"])
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass
    assert secondary.call_count == 0


async def test_embed_batch_skips_fallback_when_disabled() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small", fail=True)
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b")
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=False)

    try:
        await provider.embed_batch(["metin"])
        assert False, "EmbeddingServiceError bekleniyordu"
    except EmbeddingServiceError:
        pass
    assert secondary.call_count == 0


def test_embedding_identity_reflects_primary_before_any_call() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small")
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", dimension=1024)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    assert provider.name == "openai"
    assert provider.model == "text-embedding-3-small"
    assert provider.dimension == 3


async def test_embedding_identity_reflects_secondary_after_fallback() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small", fail=True)
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", dimension=1024)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    await provider.embed_batch(["metin"])

    assert provider.name == "ollama-qwen3-embedding-0-6b"
    assert provider.model == "qwen3-embedding:0.6b"
    assert provider.dimension == 1024


async def test_embedding_close_closes_both_providers() -> None:
    primary = _FakeEmbeddingProvider("openai", "text-embedding-3-small")
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b")
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    await provider.close()

    assert primary.closed
    assert secondary.closed


async def test_concurrent_tasks_do_not_leak_identity_across_each_other() -> None:
    """`get_embedding_provider()` `@lru_cache`'li tek bir paylaşılan örnek
    döndürüyor — bu test, o paylaşılan örneğin eşzamanlı iki isteği (biri
    fallback'e düşen, biri düşmeyen) birbirine karıştırmadığını kanıtlıyor.
    Düz bir instance attribute burada başarısız olurdu (bkz. `fallback.py`
    modül docstring'i, ADR-0024) — bu test contextvar tasarımının gerekçesi."""
    primary = _FakeEmbeddingProvider(
        "openai", "text-embedding-3-small", fail_trigger="fail-me", yield_before_return=True
    )
    secondary = _FakeEmbeddingProvider("ollama-qwen3-embedding-0-6b", "qwen3-embedding:0.6b", dimension=1024)
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    async def _run_and_report(texts: list[str]) -> str:
        await provider.embed_batch(texts)
        return provider.name

    failing_result, succeeding_result = await asyncio.gather(
        _run_and_report(["fail-me"]),
        _run_and_report(["normal metin"]),
    )

    assert failing_result == "ollama-qwen3-embedding-0-6b"
    assert succeeding_result == "openai"

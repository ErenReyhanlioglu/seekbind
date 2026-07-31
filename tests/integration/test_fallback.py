"""`backend/services/fallback.py` için gerçek Ollama'ya karşı entegrasyon testleri.

İkincil (secondary) sağlayıcı olarak GERÇEK `OllamaLLM`/`OllamaEmbedding`
kullanılır — birincil (primary) ise her zaman başarısız olan sahte bir
provider, OpenAI'a hiç gidilmez (para harcanmaz). Amaç: `FallbackLLMProvider`/
`FallbackEmbeddingProvider`'ın gerçek HTTP yolunu (Ollama'nın OpenAI-uyumlu
/v1 endpoint'i) doğru kurup kurmadığını kanıtlamak — `test_fallback.py`
(unit) aynı mantığı sahte secondary'lerle zaten test ediyor, burası sadece
gerçek ağ/protokol davranışını doğruluyor.

Bu testler docker-compose ile gelmeyen, native kurulu bir Ollama sunucusu
gerektirir (bkz. `requires_ollama` marker, `pyproject.toml`).
"""

import pytest

from backend.services.embedding import EmbeddingServiceError, OllamaEmbedding
from backend.services.fallback import FallbackEmbeddingProvider, FallbackLLMProvider
from backend.services.llm import ChatMessage, LLMResponse, LLMServiceError, OllamaLLM

pytestmark = [pytest.mark.integration, pytest.mark.requires_ollama]


class _AlwaysFailingLLMProvider:
    name = "always-failing"
    model = "always-failing-model"

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
        raise LLMServiceError("kasıtlı test hatası")

    async def close(self) -> None:
        pass


class _AlwaysFailingEmbeddingProvider:
    name = "always-failing"
    model = "always-failing-model"
    dimension = 0

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingServiceError("kasıtlı test hatası")

    async def close(self) -> None:
        pass


async def test_fallback_llm_uses_real_ollama_when_primary_fails() -> None:
    primary = _AlwaysFailingLLMProvider()
    secondary = OllamaLLM()
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    try:
        response = await provider.complete([ChatMessage(role="user", content="merhaba, kısaca kendini tanıt")])
        assert response.provider == "ollama"
        assert response.content != ""
    finally:
        await secondary.close()


async def test_fallback_embedding_uses_real_ollama_when_primary_fails() -> None:
    primary = _AlwaysFailingEmbeddingProvider()
    secondary = OllamaEmbedding()
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    try:
        [vector] = await provider.embed_batch(["entegrasyon testi metni"])
        # secondary.dimension'a karşı doğrulanır (hardcoded bir sayıya değil) —
        # OLLAMA_EMBEDDING_MODEL hangi model olursa olsun (qwen3-embedding:0.6b,
        # embeddingmagibu-200m vb.) test aynı şekilde geçerli kalır.
        assert len(vector) == secondary.dimension
        assert provider.name == secondary.name
    finally:
        await secondary.close()

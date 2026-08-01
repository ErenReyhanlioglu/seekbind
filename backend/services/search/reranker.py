"""Cross-encoder reranking — RRF aday havuzunu Jina AI'nin hosted rerank
API'siyle yeniden sıralar.

Yerel bir model (örn. bge-reranker-v2-m3) yerine hosted API tercih edildi:
ağır ML bağımlılığı (torch/transformers) ve CPU inference gecikme riski
yok, Jina'nın kendi BEIR/MKQA/AirBench sonuçlarına göre bge-reranker-v2-m3'ten
daha kaliteli ve daha hızlı (bkz. docs/roadmap.md "Önemli kararlar"). Birden
fazla sağlayıcı ileride eklenebilir diye (örn. yerel bir model) Protocol ile
soyutlanmıştır.
"""

from functools import lru_cache
from typing import Protocol

import httpx

from backend.config import get_settings

JINA_RERANK_URL: str = "https://api.jina.ai/v1/rerank"


class RerankerServiceError(Exception):
    """Reranking başarısız olduğunda fırlatılır."""


class RerankerProvider(Protocol):
    """Reranker sağlayıcıları için ortak arayüz."""

    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        """documents listesindeki metinleri query'ye göre azalan skorla sıralar.

        Döndürülen (index, relevance_score) çiftlerindeki index, documents
        listesindeki orijinal pozisyona karşılık gelir.
        """
        ...

    async def close(self) -> None:
        """Açık HTTP bağlantılarını kapatır (graceful shutdown için)."""
        ...


class JinaReranker:
    """Jina AI'nin hosted rerank API'siyle (varsayılan: jina-reranker-v3) cross-encoder reranking."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.jina_api_key.get_secret_value()
        self._model = settings.jina_reranker_model
        # httpx.AsyncClient her istekte değil, bir kere oluşturulup saklanır
        # (CLAUDE.md: "pahalı client'ları singleton tut") — kapatılması
        # close()'a bırakılır, lifespan shutdown'da çağrılır.
        self._client = httpx.AsyncClient(timeout=settings.jina_rerank_timeout_seconds)

    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        """Jina'nın rerank endpoint'ine istek atar, (index, relevance_score) döner."""
        if not documents:
            return []
        try:
            response = await self._client.post(
                JINA_RERANK_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_n,
                    "return_documents": False,
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as e:
            raise RerankerServiceError("Jina rerank isteği zaman aşımına uğradı") from e
        except httpx.HTTPStatusError as e:
            raise RerankerServiceError(f"Jina rerank API hatası: {e}") from e

        results = response.json()["results"]
        return [(item["index"], item["relevance_score"]) for item in results]

    async def close(self) -> None:
        """httpx.AsyncClient'ı kapatır."""
        await self._client.aclose()


@lru_cache
def get_reranker_provider() -> RerankerProvider:
    """Kullanılacak reranker sağlayıcısını önbellekten döner."""
    return JinaReranker()

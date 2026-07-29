"""RAG orkestrasyonu — serbest metin sorgudan öneri üretimi.

Üç adım: (1) LLM ile serbest metni yapılandırılmış filtrelere ve semantik
sorguya ayrıştırma (`intent.py`), (2) mevcut `search_providers()`'ı
değiştirmeden çağırma, (3) sonuçlardan LLM ile doğal dilde öneri üretme
(`recommendation.py`).

İki fallback katmanı var: intent parsing tamamen başarısız olursa ham sorgu
+ boş `SearchFilters()` ile salt semantik aramaya sessizce düşülür (bkz.
`_resolve_search_query_and_filters`). Öneri üretimi başarısız olursa sabit
bir mesaja düşülür, arama sonuçları yine de döner (bkz.
`_generate_recommendation_with_fallback`).

Sağlayıcılar arası otomatik fallback (OpenAI hata verirse Ollama'ya geçme)
ve Langfuse çok-adımlı trace gruplama bilinçli olarak burada değil — bkz.
docs/roadmap.md `feature/fallback-mechanism` / `feature/langfuse-integration`.
"""

import logging
from datetime import date

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import ProviderResult, RecommendationResponse
from backend.services.embedding import EmbeddingProvider
from backend.services.llm import LLMProvider
from backend.services.rag.intent import (
    IntentParsingError,
    build_availability_filter,
    build_search_filters,
    parse_intent,
)
from backend.services.rag.recommendation import RecommendationGenerationError, generate_recommendation
from backend.services.search import (
    BM25Index,
    DateAvailabilityFilter,
    RerankerProvider,
    SearchFilters,
    search_providers,
)

logger = logging.getLogger(__name__)

EMPTY_RESULTS_MESSAGE: str = "Aramanıza uygun bir işletme bulamadım, farklı bir arama deneyebilirsin."
RECOMMENDATION_FALLBACK_MESSAGE: str = "Aşağıda arama sonuçlarını bulabilirsin."


async def _resolve_search_query_and_filters(
    llm_provider: LLMProvider, raw_query: str, today: date
) -> tuple[str, SearchFilters, DateAvailabilityFilter | None]:
    """Intent parsing dener, başarısız olursa ham sorgu + boş filtreye düşer."""
    try:
        intent = await parse_intent(llm_provider, raw_query, today)
    except IntentParsingError as e:
        logger.warning("Intent parsing başarısız, salt semantik aramaya düşülüyor: %s", e)
        return raw_query, SearchFilters(), None
    return intent.semantic_query, build_search_filters(intent), build_availability_filter(intent, today)


async def _generate_recommendation_with_fallback(
    llm_provider: LLMProvider, raw_query: str, results: list[ProviderResult]
) -> str:
    """Öneri üretimi başarısız olursa sabit bir mesaja düşer, sonuçlar yine de döner."""
    try:
        return await generate_recommendation(llm_provider, raw_query, results)
    except RecommendationGenerationError as e:
        logger.warning("Öneri üretimi başarısız, sabit mesaja düşülüyor: %s", e)
        return RECOMMENDATION_FALLBACK_MESSAGE


async def get_recommendation(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    llm_provider: LLMProvider,
    raw_query: str,
    today: date,
    limit: int = 10,
    offset: int = 0,
) -> RecommendationResponse:
    """Tüm akışı orkestre eder: intent parse -> arama -> öneri üretimi.

    `search_providers()`'ın altyapısı (DB/Qdrant) sağlıklı olduğu sürece HER
    ZAMAN bir `RecommendationResponse` döner — `IntentParsingError` ve
    `RecommendationGenerationError` asla bu fonksiyonun dışına sızmaz.

    `today` hiçbir zaman varsayılan değer almamalı (çağıran, `date.today()`'i
    kendi gövdesinde çağırmalı) — fonksiyon imzasında `= date.today()` gibi
    bir varsayılan, sunucu ne zaman başladıysa o ana donardı.
    """
    search_query, filters, availability = await _resolve_search_query_and_filters(llm_provider, raw_query, today)

    search_response = await search_providers(
        session=session,
        qdrant_client=qdrant_client,
        bm25_index=bm25_index,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        query=search_query,
        filters=filters,
        availability=availability,
        limit=limit,
        offset=offset,
    )

    if not search_response.results:
        return RecommendationResponse(recommendation=EMPTY_RESULTS_MESSAGE, results=[], total=0)

    recommendation_text = await _generate_recommendation_with_fallback(
        llm_provider, raw_query, search_response.results
    )
    return RecommendationResponse(
        recommendation=recommendation_text,
        results=search_response.results,
        total=search_response.total,
    )

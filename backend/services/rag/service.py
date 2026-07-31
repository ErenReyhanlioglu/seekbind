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

`get_recommendation()`, `@observe()` ile tek bir Langfuse trace'i olarak
izlenir — içindeki 2 LLM çağrısı (intent parsing + öneri üretimi,
`langfuse.openai.AsyncOpenAI` sarmalayıcısıyla otomatik izlenir) bu trace'in
altına, `observe`'ün contextvar tabanlı gözlem yığını sayesinde otomatik
nest olur (manuel `trace_id` taşımaya gerek yok). İsteğin tamamına ait özet
(ayrıştırılan filtreler, fallback'ler, sonuç sayısı) `_record_trace` ile
trace metadata'sına yazılır.

Sağlayıcılar arası otomatik fallback (OpenAI hata verirse Ollama'ya geçme)
bilinçli olarak burada değil — bkz. docs/roadmap.md `feature/fallback-mechanism`.
"""

import logging
from datetime import date

from langfuse.decorators import langfuse_context, observe
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
from backend.services.user_location import get_user_reference_location
from backend.services.rag.recommendation import RecommendationGenerationError, generate_recommendation
from backend.services.search import (
    BM25Index,
    DateAvailabilityFilter,
    RatingPreference,
    RerankerProvider,
    SearchFilters,
    search_providers,
)

logger = logging.getLogger(__name__)

EMPTY_RESULTS_MESSAGE: str = "Aramanıza uygun bir işletme bulamadım, farklı bir arama deneyebilirsin."
RECOMMENDATION_FALLBACK_MESSAGE: str = "Aşağıda arama sonuçlarını bulabilirsin."
_LANGFUSE_TRACE_NAME: str = "recommend"


async def _resolve_search_query_and_filters(
    llm_provider: LLMProvider, raw_query: str, today: date, session: AsyncSession
) -> tuple[str, SearchFilters, DateAvailabilityFilter | None, RatingPreference | None, bool, bool, bool]:
    """Intent parsing dener, başarısız olursa ham sorgu + boş filtreye düşer.

    Sondan iki önceki eleman (`bool`), intent parsing'in fallback'e düşüp
    düşmediğini belirtir; sondan bir önceki eleman (`bool`) `near_me`
    sinyalidir; son eleman (`bool`) intent parsing LLM cevabının Redis
    cache'inden gelip gelmediğidir (bkz. `parse_intent`) — üçü de
    `get_recommendation` tarafından kullanılır (trace metadata'sı ve
    `distance_reference` çözümlemesi için).
    """
    try:
        intent, intent_cache_hit = await parse_intent(llm_provider, raw_query, today)
    except IntentParsingError as e:
        logger.warning("Intent parsing başarısız, salt semantik aramaya düşülüyor: %s", e)
        return raw_query, SearchFilters(), None, None, True, False, False
    filters = await build_search_filters(intent, session)
    availability = build_availability_filter(intent, today)
    return (
        intent.semantic_query,
        filters,
        availability,
        intent.rating_preference,
        False,
        intent.near_me,
        intent_cache_hit,
    )


async def _resolve_distance_reference(
    session: AsyncSession, user_id: int, near_me: bool
) -> tuple[float, float] | None:
    """`near_me` true ise kullanıcının referans konumunu döner, değilse None.

    Konum bilinmiyorsa (bkz. `get_user_reference_location`) da sessizce None
    döner — `search_providers`'ta bu, mesafe sinyali hiç uygulanmamış gibi
    davranır, aramayı çökertmez.
    """
    if not near_me:
        return None
    return await get_user_reference_location(session, user_id)


async def _generate_recommendation_with_fallback(
    llm_provider: LLMProvider,
    raw_query: str,
    results: list[ProviderResult],
    rating_preference: RatingPreference | None,
) -> tuple[str, bool]:
    """Öneri üretimi başarısız olursa sabit bir mesaja düşer, sonuçlar yine de döner.

    Son eleman (`bool`), öneri üretiminin fallback'e düşüp düşmediğini belirtir.
    """
    try:
        text = await generate_recommendation(llm_provider, raw_query, results, rating_preference)
        return text, False
    except RecommendationGenerationError as e:
        logger.warning("Öneri üretimi başarısız, sabit mesaja düşülüyor: %s", e)
        return RECOMMENDATION_FALLBACK_MESSAGE, True


def _build_trace_metadata(
    *,
    search_query: str,
    filters: SearchFilters,
    availability: DateAvailabilityFilter | None,
    rating_preference: RatingPreference | None,
    near_me: bool,
    distance_reference: tuple[float, float] | None,
    intent_fallback: bool,
    intent_cache_hit: bool,
    recommendation_fallback: bool,
    result_count: int,
    total: int,
    limit: int,
    offset: int,
) -> dict[str, object]:
    """Tüm `/recommend` isteğinin özetini Langfuse trace metadata'sına döker.

    `intent.py`/`recommendation.py`'nin kendi LLM çağrı metadata'sı sadece o
    adıma özgüyken, bu istek genelinde neyin ayrıştığını/döndüğünü tek
    yerde toplar.
    """
    return {
        "search_query": search_query,
        "category": filters.category,
        "min_price": filters.min_price,
        "max_price": filters.max_price,
        "gender": filters.gender,
        "online_only": filters.online_only,
        "weekend_open_only": filters.weekend_open_only,
        "rating_preference": rating_preference,
        "near_me": near_me,
        "distance_reference_resolved": distance_reference is not None,
        "availability_date": availability.date.isoformat() if availability else None,
        "availability_time_of_day": availability.time_of_day if availability else None,
        "intent_parsing_fallback": intent_fallback,
        "intent_cache_hit": intent_cache_hit,
        "recommendation_fallback": recommendation_fallback,
        "result_count": result_count,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _build_trace_tags(*, intent_fallback: bool, recommendation_fallback: bool, empty_results: bool) -> list[str]:
    """Langfuse arayüzünde filtrelemeyi kolaylaştıran etiketler üretir."""
    tags = [_LANGFUSE_TRACE_NAME]
    if intent_fallback:
        tags.append("intent_fallback")
    if recommendation_fallback:
        tags.append("recommendation_fallback")
    if empty_results:
        tags.append("empty_results")
    return tags


def _record_trace(
    *,
    raw_query: str,
    output: str,
    search_query: str,
    filters: SearchFilters,
    availability: DateAvailabilityFilter | None,
    rating_preference: RatingPreference | None,
    near_me: bool,
    distance_reference: tuple[float, float] | None,
    intent_fallback: bool,
    intent_cache_hit: bool,
    recommendation_fallback: bool,
    result_count: int,
    total: int,
    limit: int,
    offset: int,
) -> None:
    """İsteğin özetini aktif Langfuse trace'ine yazar (bkz. get_recommendation)."""
    langfuse_context.update_current_trace(
        input=raw_query,
        output=output,
        tags=_build_trace_tags(
            intent_fallback=intent_fallback,
            recommendation_fallback=recommendation_fallback,
            empty_results=result_count == 0,
        ),
        metadata=_build_trace_metadata(
            search_query=search_query,
            filters=filters,
            availability=availability,
            rating_preference=rating_preference,
            near_me=near_me,
            distance_reference=distance_reference,
            intent_fallback=intent_fallback,
            intent_cache_hit=intent_cache_hit,
            recommendation_fallback=recommendation_fallback,
            result_count=result_count,
            total=total,
            limit=limit,
            offset=offset,
        ),
    )


@observe(name=_LANGFUSE_TRACE_NAME, capture_input=False, capture_output=False)
async def get_recommendation(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    llm_provider: LLMProvider,
    raw_query: str,
    user_id: int,
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

    `user_id` zorunlu — SeekBind kişiselleştirilebilir bir öneri sistemi
    hedeflediği için aramanın her zaman bir kullanıcıya bağlı olması tutarlı
    (bkz. `RecommendRequest` docstring'i). Şu an tek somut kullanım yeri:
    intent'te `near_me` true çıkarsa, kullanıcının `UserProfile` referans
    konumu `distance_reference` olarak `search_providers()`'a iletilir.

    `capture_input=False, capture_output=False`: bu fonksiyonun argümanları
    (`session`, `qdrant_client` gibi servis nesneleri) otomatik JSON'a
    çevrilmeye çalışılırsa dağınık/gereksiz veri üretir — trace'e ne
    yazılacağı bilinçli olarak `_record_trace` ile elle seçilir.
    """
    search_query, filters, availability, rating_preference, intent_fallback, near_me, intent_cache_hit = (
        await _resolve_search_query_and_filters(llm_provider, raw_query, today, session)
    )
    distance_reference = await _resolve_distance_reference(session, user_id, near_me)

    search_response = await search_providers(
        session=session,
        qdrant_client=qdrant_client,
        bm25_index=bm25_index,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        query=search_query,
        filters=filters,
        availability=availability,
        rating_preference=rating_preference,
        distance_reference=distance_reference,
        limit=limit,
        offset=offset,
    )

    if not search_response.results:
        _record_trace(
            raw_query=raw_query,
            output=EMPTY_RESULTS_MESSAGE,
            search_query=search_query,
            filters=filters,
            availability=availability,
            rating_preference=rating_preference,
            near_me=near_me,
            distance_reference=distance_reference,
            intent_fallback=intent_fallback,
            intent_cache_hit=intent_cache_hit,
            recommendation_fallback=False,
            result_count=0,
            total=0,
            limit=limit,
            offset=offset,
        )
        return RecommendationResponse(recommendation=EMPTY_RESULTS_MESSAGE, results=[], total=0)

    recommendation_text, recommendation_fallback = await _generate_recommendation_with_fallback(
        llm_provider, raw_query, search_response.results, rating_preference
    )
    _record_trace(
        raw_query=raw_query,
        output=recommendation_text,
        search_query=search_query,
        filters=filters,
        availability=availability,
        rating_preference=rating_preference,
        near_me=near_me,
        distance_reference=distance_reference,
        intent_fallback=intent_fallback,
        intent_cache_hit=intent_cache_hit,
        recommendation_fallback=recommendation_fallback,
        result_count=len(search_response.results),
        total=search_response.total,
        limit=limit,
        offset=offset,
    )
    return RecommendationResponse(
        recommendation=recommendation_text,
        results=search_response.results,
        total=search_response.total,
    )

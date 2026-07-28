"""search_providers — hybrid arama orkestrasyonu.

Sırayla: (1) vektör + BM25'ten aday çekilir (BM25 sonuçları, hard filtre
varsa Qdrant'tan çekilen filtrelenmiş ID kümesiyle kesişime sokulur —
rank-bm25 kendi başına payload filtering desteklemediği için), (2) RRF ile
birleştirilir, (3) varsa tarih/saat müsaitliğine göre ikinci fazda daraltılır,
(4) aday işletmelerin verisi çekilir, (5) cross-encoder reranker ile yeniden
sıralanır (başarısız olursa RRF sırası korunur, arama çökmez), (6) limit/offset
ile dilimlenir, (7) response şemasına eşlenir.
"""

import logging

from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import ProviderResult, SearchResponse
from backend.db.models import Business
from backend.services.embedding import EmbeddingProvider
from backend.services.search.availability import DateAvailabilityFilter, fetch_available_business_ids
from backend.services.search.bm25 import BM25Index, build_lexical_text
from backend.services.search.filters import NearFilter, SearchFilters, compute_distance_km, translate_filters_to_qdrant
from backend.services.search.fusion import reciprocal_rank_fusion
from backend.services.search.reranker import RerankerProvider, RerankerServiceError
from backend.services.search.vector import fetch_filtered_business_ids, vector_search

logger = logging.getLogger(__name__)

CANDIDATE_DEPTH_PER_SOURCE: int = 30
CANDIDATE_POOL_SIZE: int = 40


async def _fetch_businesses_by_id(session: AsyncSession, business_ids: list[int]) -> list[Business]:
    """Verilen ID'lere ait işletmeleri, ID listesinin sırasını koruyarak döner.

    SQL'in IN (...) koşulu sıra garanti etmediği için sonuç, DB'den gelen
    haliyle değil, çağıranın verdiği (RRF/müsaitlik sonrası anlamlı) sırayla
    döndürülür.
    """
    if not business_ids:
        return []
    result = await session.execute(select(Business).where(Business.id.in_(business_ids)))
    businesses_by_id = {business.id: business for business in result.scalars().all()}
    return [businesses_by_id[bid] for bid in business_ids if bid in businesses_by_id]


async def _rerank_businesses(
    reranker_provider: RerankerProvider,
    query: str,
    businesses: list[Business],
) -> list[Business]:
    """İşletmeleri cross-encoder reranker ile yeniden sıralar.

    Reranker başarısız olursa (zaman aşımı, API hatası) tüm aramayı
    çökertmek yerine mevcut (RRF/müsaitlik sonrası) sıra korunur —
    CLAUDE.md'nin fallback ilkesi: reranksiz ama yine de mantıklı bir
    sonuç dönmeye devam eder.
    """
    if not businesses:
        return businesses
    documents = [build_lexical_text(business) for business in businesses]
    try:
        ranked = await reranker_provider.rerank(query, documents, top_n=len(documents))
    except RerankerServiceError as e:
        logger.warning("Reranker başarısız, RRF sırası korunuyor: %s", e)
        return businesses
    return [businesses[index] for index, _ in ranked]


def _to_provider_result(business: Business, near: NearFilter | None) -> ProviderResult:
    """Business ORM nesnesini ProviderResult response şemasına eşler."""
    distance_km = None
    if near is not None and business.latitude is not None and business.longitude is not None:
        distance_km = compute_distance_km(near.latitude, near.longitude, business.latitude, business.longitude)
    return ProviderResult(
        id=business.id,
        title=business.title,
        type_normalized=business.type_normalized,
        rating=business.rating,
        weighted_rating=business.weighted_rating,
        price_min=business.price_min,
        price_max=business.price_max,
        address=business.address,
        phone=business.phone,
        online_available=business.online_available,
        gender=business.gender,
        services=business.services,
        tags=business.tags,
        rich_description=business.rich_description,
        distance_km=distance_km,
    )


async def search_providers(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    query: str,
    filters: SearchFilters,
    availability: DateAvailabilityFilter | None = None,
    limit: int = 10,
    offset: int = 0,
) -> SearchResponse:
    """Hybrid (semantik + lexical) arama yapar, hard filtreleri ve opsiyonel
    tarih/saat müsaitliğini uygular, cross-encoder ile yeniden sıralar,
    sayfalanmış sonuçları döner."""
    qdrant_filter = translate_filters_to_qdrant(filters)

    vector_results = await vector_search(
        qdrant_client, embedding_provider, query, CANDIDATE_DEPTH_PER_SOURCE, qdrant_filter
    )

    bm25_results = bm25_index.search(query, CANDIDATE_DEPTH_PER_SOURCE)
    if qdrant_filter is not None:
        # BM25 kendi başına hard filtre bilmiyor — filtreyi sağlayan ID
        # kümesiyle kesişim alınır. Filtre yoksa bu ekstra Qdrant sorgusu
        # atlanır (is_active zaten BM25 corpus'unda garanti, bkz. bm25.py).
        filtered_ids = await fetch_filtered_business_ids(qdrant_client, embedding_provider, qdrant_filter)
        bm25_results = [pair for pair in bm25_results if pair[0] in filtered_ids]

    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    candidate_ids = [business_id for business_id, _ in fused][:CANDIDATE_POOL_SIZE]

    if availability is not None:
        available_ids = await fetch_available_business_ids(session, candidate_ids, availability)
        candidate_ids = [business_id for business_id in candidate_ids if business_id in available_ids]

    candidates = await _fetch_businesses_by_id(session, candidate_ids)
    candidates = await _rerank_businesses(reranker_provider, query, candidates)

    page = candidates[offset : offset + limit]
    results = [_to_provider_result(business, filters.near) for business in page]

    return SearchResponse(results=results, total=len(candidates))

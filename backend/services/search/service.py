"""search_providers — hybrid arama orkestrasyonu.

Sırayla: (1) vektör + BM25'ten aday çekilir (BM25 sonuçları, hard filtre
varsa Qdrant'tan çekilen filtrelenmiş ID kümesiyle kesişime sokulur —
rank-bm25 kendi başına payload filtering desteklemediği için), (2) RRF ile
birleştirilir, (3) varsa tarih/saat müsaitliğine göre ikinci fazda daraltılır,
(4) aday işletmelerin verisi çekilir, (5) cross-encoder reranker ile yeniden
sıralanır (başarısız olursa RRF sırası korunur, arama çökmez), (6) varsa
puan tercihi ve/veya mesafe referansına göre son bir sıralama uygulanır
(ADR-0015, mesafe RRF ile birleştirilir — bkz. `apply_final_sort`), (7)
limit/offset ile dilimlenir, (8) response şemasına eşlenir.
"""

import logging
from typing import Literal, cast

from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import ProviderResult, SearchResponse
from backend.db.models import Business
from backend.services.embedding import EmbeddingProvider
from backend.services.search.availability import (
    DateAvailabilityFilter,
    fetch_available_business_ids,
)
from backend.services.search.bm25 import BM25Index, build_lexical_text
from backend.services.search.filters import (
    SearchFilters,
    compute_distance_km,
    translate_filters_to_qdrant,
)
from backend.services.search.fusion import reciprocal_rank_fusion
from backend.services.search.reranker import RerankerProvider, RerankerServiceError
from backend.services.search.vector import fetch_filtered_business_ids, vector_search

logger = logging.getLogger(__name__)

CANDIDATE_DEPTH_PER_SOURCE: int = 30
CANDIDATE_POOL_SIZE: int = 40

# "en iyi"/"en kötü" gibi açık üstünlük ifadeleri için — bir eşik/filtre değil,
# rerank sonrası son bir SIRALAMA sinyali (bkz. ADR-0015). price_preference'tan
# farklı olarak Qdrant'a hiç gitmiyor: "ucuz"/"pahalı" bir eşik ifade eder ama
# "en iyi"/"en kötü" tüm sonuçların o sırada dizilmesini ister, birini
# elemeyi değil.
RatingPreference = Literal["high", "low"]


async def _fetch_businesses_by_id(
    session: AsyncSession, business_ids: list[int]
) -> list[Business]:
    """Verilen ID'lere ait işletmeleri, ID listesinin sırasını koruyarak döner.

    SQL'in IN (...) koşulu sıra garanti etmediği için sonuç, DB'den gelen
    haliyle değil, çağıranın verdiği (RRF/müsaitlik sonrası anlamlı) sırayla
    döndürülür.
    """
    if not business_ids:
        return []
    result = await session.execute(
        select(Business).where(Business.id.in_(business_ids))
    )
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


def _rank_by_rating(
    businesses: list[Business], preference: RatingPreference
) -> list[tuple[int, float]]:
    """weighted_rating'i olan işletmeleri tercihe göre sıralar (yüksekten
    düşüğe ya da düşükten yükseğe), `weighted_rating`'i olmayanları YÖN FARK
    ETMEKSİZİN listenin sonuna ekler — TÜM işletmeleri içeren bir sıralı
    (business_id, 0.0) listesi döner (RRF'e girdi olacak şekilde; skor
    değeri önemsiz, sadece sıradaki konumu kullanılır).

    Puanı bilinmeyen bir işletme ne "en iyi" ne "en kötü" olarak iddia
    edilemez (bkz. ADR-0004'ün Bayesian düzeltmesi — az/hiç yorumu olan
    işletmelerde `weighted_rating` None kalır); bu yüzden "low" tercihinde
    bile puansızlar en üste değil, en alta gider. Listenin TAMAMINI (puansızlar
    dahil) döndürmek kritik — RRF, bir listede hiç yer almayan id'yi o
    listeden katkı almadan bırakır, ama listede DIŞARIDA bırakılırsa (sona
    eklenmek yerine) tekil sinyal durumunda dahi sonuçtan tamamen düşer.
    """
    rated = [
        business for business in businesses if business.weighted_rating is not None
    ]
    unrated = [business for business in businesses if business.weighted_rating is None]
    # cast: bu noktada rated'daki her business'ın weighted_rating'i yukarıdaki
    # filtreyle zaten None değil — Pyright bunu liste comprehension'ı üzerinden
    # takip edemiyor (ORM attribute, statik olarak float | None kalıyor).
    rated.sort(
        key=lambda business: cast(float, business.weighted_rating),
        reverse=(preference == "high"),
    )
    return [(business.id, 0.0) for business in rated + unrated]


def _rank_by_distance(
    businesses: list[Business],
    reference: tuple[float, float],
    online_exempt: bool,
) -> list[tuple[int, float]]:
    """İşletmeleri referans konuma (lat, lon) yakınlığa göre sıralar.

    Konumu bilinmeyen (`latitude`/`longitude` None) işletmeler ve —
    `online_exempt` True ise — online hizmet veren işletmeler bu listeye
    HİÇ dahil edilmez: mesafe konusunda "görüşü yok" sayılırlar, RRF'de bu
    sinyalden katkı almazlar (cezalandırılmaz ya da ödüllendirilmezler,
    tek başına ratingle aynı sonucu alırlar — _rank_by_rating'teki
    "sona ekleme" ile aynı sonuç, ayrı bir yerde çağıran taraf tamamlar).
    """
    ref_lat, ref_lon = reference
    eligible = [
        business
        for business in businesses
        if business.latitude is not None
        and business.longitude is not None
        and not (online_exempt and business.online_available)
    ]
    eligible.sort(key=lambda business: compute_distance_km(ref_lat, ref_lon, business.latitude, business.longitude))  # type: ignore[arg-type]
    return [(business.id, 0.0) for business in eligible]


def apply_final_sort(
    businesses: list[Business],
    rating_preference: RatingPreference | None,
    distance_reference: tuple[float, float] | None,
    online_exempt_from_distance: bool = True,
) -> list[Business]:
    """Puan tercihi ve/veya mesafe referansına göre son bir sıralama uygular.

    İkisi de verilmişse mevcut `reciprocal_rank_fusion` ile birleştirilir —
    yeni bir "blend score" formülü icat etmek yerine, BM25+vektör füzyonunda
    zaten kullanılan aynı mekanizma (ADR-0015'te bilinçli olarak tercih
    edildiği gibi). Sadece biri verilmişse RRF tek bir liste üzerinde
    çalışır ve o listenin sırasını aynen korur (matematiksel olarak eski
    tekil-kriter davranışına indirgenir). Hiçbiri verilmemişse mevcut sıra
    değişmeden döner.

    `_rank_by_rating`/`_rank_by_distance` bazı işletmeleri kendi listelerinden
    çıkarabildiği için (puansız / online-muaf), RRF sonucunda hiçbir sinyale
    dahil olmayan işletmeler kalabilir — bunlar da en sona eklenir.
    """
    rankings: list[list[tuple[int, float]]] = []
    if rating_preference is not None:
        rankings.append(_rank_by_rating(businesses, rating_preference))
    if distance_reference is not None:
        rankings.append(
            _rank_by_distance(
                businesses, distance_reference, online_exempt_from_distance
            )
        )

    if not rankings:
        return businesses

    fused = reciprocal_rank_fusion(rankings)
    businesses_by_id = {business.id: business for business in businesses}
    ordered = [
        businesses_by_id[business_id]
        for business_id, _ in fused
        if business_id in businesses_by_id
    ]
    included_ids = {business_id for business_id, _ in fused}
    leftover = [business for business in businesses if business.id not in included_ids]
    return ordered + leftover


def _to_provider_result(
    business: Business, distance_reference: tuple[float, float] | None
) -> ProviderResult:
    """Business ORM nesnesini ProviderResult response şemasına eşler."""
    distance_km = None
    if (
        distance_reference is not None
        and business.latitude is not None
        and business.longitude is not None
    ):
        ref_lat, ref_lon = distance_reference
        distance_km = compute_distance_km(
            ref_lat, ref_lon, business.latitude, business.longitude
        )
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
    rating_preference: RatingPreference | None = None,
    distance_reference: tuple[float, float] | None = None,
    limit: int = 10,
    offset: int = 0,
) -> SearchResponse:
    """Hybrid (semantik + lexical) arama yapar, hard filtreleri ve opsiyonel
    tarih/saat müsaitliğini uygular, cross-encoder ile yeniden sıralar,
    sayfalanmış sonuçları döner.

    `distance_reference` verilirse (kullanıcının referans konumu), rating
    tercihiyle birlikte ya da tek başına son sıralamaya katılır (bkz.
    `apply_final_sort`) — bir yarıçap filtresi DEĞİL, yalnızca bir sıralama
    sinyalidir (bkz. NearFilter ile karışmasın diye service.py başındaki not).
    """
    qdrant_filter = translate_filters_to_qdrant(filters)

    vector_results = await vector_search(
        qdrant_client,
        embedding_provider,
        query,
        CANDIDATE_DEPTH_PER_SOURCE,
        qdrant_filter,
    )

    bm25_results = bm25_index.search(query, CANDIDATE_DEPTH_PER_SOURCE)
    if qdrant_filter is not None:
        # BM25 kendi başına hard filtre bilmiyor — filtreyi sağlayan ID
        # kümesiyle kesişim alınır. Filtre yoksa bu ekstra Qdrant sorgusu
        # atlanır (is_active zaten BM25 corpus'unda garanti, bkz. bm25.py).
        filtered_ids = await fetch_filtered_business_ids(
            qdrant_client, embedding_provider, qdrant_filter
        )
        bm25_results = [pair for pair in bm25_results if pair[0] in filtered_ids]

    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    candidate_ids = [business_id for business_id, _ in fused][:CANDIDATE_POOL_SIZE]

    if availability is not None:
        available_ids = await fetch_available_business_ids(
            session, candidate_ids, availability
        )
        candidate_ids = [
            business_id for business_id in candidate_ids if business_id in available_ids
        ]

    candidates = await _fetch_businesses_by_id(session, candidate_ids)
    candidates = await _rerank_businesses(reranker_provider, query, candidates)

    if rating_preference is not None or distance_reference is not None:
        # online_exempt_from_distance=not filters.online_only: kullanıcı
        # AÇIKÇA online_only istediyse online işletmeler artık mesafe
        # sıralamasından muaf tutulmaz (bkz. apply_final_sort docstring'i).
        candidates = apply_final_sort(
            candidates,
            rating_preference,
            distance_reference,
            online_exempt_from_distance=not filters.online_only,
        )

    page = candidates[offset : offset + limit]
    results = [_to_provider_result(business, distance_reference) for business in page]

    return SearchResponse(results=results, total=len(candidates))

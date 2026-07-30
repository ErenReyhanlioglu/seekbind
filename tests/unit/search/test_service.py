"""backend/services/search/service.py için birim testler."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.db.models import Business
from backend.services.search.availability import DateAvailabilityFilter
from backend.services.search.bm25 import BM25Index
from backend.services.search.filters import SearchFilters
from backend.services.search.reranker import RerankerServiceError
from backend.services.search.service import (
    _fetch_businesses_by_id,
    _rank_by_distance,
    _rank_by_rating,
    _rerank_businesses,
    _to_provider_result,
    apply_final_sort,
    search_providers,
)


def _make_business(
    business_id: int = 1,
    title: str = "Test Diş Kliniği",
    services: list[str] | None = None,
    rich_description: str = "Açıklama",
    keywords: list[str] | None = None,
    latitude: float | None = 40.77,
    longitude: float | None = 29.92,
    weighted_rating: float | None = 4.3,
    online_available: bool = False,
) -> Business:
    return Business(
        id=business_id,
        title=title,
        type_normalized="Diş Kliniği",
        rating=4.5,
        weighted_rating=weighted_rating,
        price_min=100,
        price_max=300,
        address="İzmit",
        phone="0000",
        online_available=online_available,
        gender="unisex",
        services=services if services is not None else ["dolgu"],
        tags=[],
        keywords=keywords if keywords is not None else [],
        rich_description=rich_description,
        latitude=latitude,
        longitude=longitude,
    )


def _build_bm25_index(businesses: list[Business]) -> BM25Index:
    """Gerçek BM25Index kurar — search_providers somut BM25Index tipini
    beklediği için (Protocol değil, tek implementasyon var) fake yerine
    gerçek sınıf kullanılır, bkz. filters.py/bm25.py tasarım notları.
    """
    index = BM25Index()
    index.build(businesses, fingerprint=(len(businesses), None))
    return index


def test_to_provider_result_computes_distance_when_reference_given() -> None:
    business = _make_business(latitude=40.77, longitude=29.92)

    result = _to_provider_result(business, (40.78, 29.93))

    assert result.distance_km is not None
    assert result.distance_km > 0


def test_to_provider_result_leaves_distance_none_without_reference() -> None:
    business = _make_business()

    result = _to_provider_result(business, None)

    assert result.distance_km is None


def test_to_provider_result_leaves_distance_none_when_business_has_no_coordinates() -> None:
    business = _make_business(latitude=None, longitude=None)

    result = _to_provider_result(business, (40.78, 29.93))

    assert result.distance_km is None


async def test_fetch_businesses_by_id_returns_empty_list_for_empty_input() -> None:
    """Boş ID listesi için DB'ye hiç gidilmemeli."""
    session = AsyncMock()

    result = await _fetch_businesses_by_id(session, [])

    assert result == []
    session.execute.assert_not_called()


async def test_rerank_businesses_returns_empty_list_for_empty_input() -> None:
    result = await _rerank_businesses(_IdentityRerankerProvider(), "sorgu", [])

    assert result == []


class _FailingRerankerProvider:
    """Reranker'ın zaman aşımı/API hatası gibi başarısızlık senaryolarını
    taklit eder — CLAUDE.md'nin fallback ilkesi: arama çökmemeli."""

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        raise RerankerServiceError("zaman aşımı")

    async def close(self) -> None:
        pass


async def test_rerank_businesses_falls_back_to_original_order_on_failure() -> None:
    businesses = [_make_business(business_id=1), _make_business(business_id=2)]

    result = await _rerank_businesses(_FailingRerankerProvider(), "sorgu", businesses)

    assert [b.id for b in result] == [1, 2]


def test_rank_by_rating_orders_descending_for_high_preference() -> None:
    low = _make_business(business_id=1, weighted_rating=3.0)
    high = _make_business(business_id=2, weighted_rating=4.8)

    result = _rank_by_rating([low, high], "high")

    assert [business_id for business_id, _ in result] == [2, 1]


def test_rank_by_rating_orders_ascending_for_low_preference() -> None:
    low = _make_business(business_id=1, weighted_rating=3.0)
    high = _make_business(business_id=2, weighted_rating=4.8)

    result = _rank_by_rating([high, low], "low")

    assert [business_id for business_id, _ in result] == [1, 2]


def test_rank_by_rating_appends_unrated_businesses_at_end_for_high_preference() -> None:
    """Puanı bilinmeyen bir işletme "en iyi" iddiasıyla üste çıkarılamaz —
    ADR-0015: Noter gibi hiç yorum almayan kategoriler için NULL, sona gider."""
    rated = _make_business(business_id=1, weighted_rating=4.0)
    unrated = _make_business(business_id=2, weighted_rating=None)

    result = _rank_by_rating([unrated, rated], "high")

    assert [business_id for business_id, _ in result] == [1, 2]


def test_rank_by_rating_appends_unrated_businesses_at_end_for_low_preference() -> None:
    """Aynı kural "en kötü" için de geçerli — NULL puanlı bir işletme "en
    kötü" olarak da iddia edilemez, yön fark etmeksizin sona gider."""
    rated = _make_business(business_id=1, weighted_rating=4.0)
    unrated = _make_business(business_id=2, weighted_rating=None)

    result = _rank_by_rating([unrated, rated], "low")

    assert [business_id for business_id, _ in result] == [1, 2]


def test_rank_by_rating_returns_empty_list_unchanged() -> None:
    assert _rank_by_rating([], "high") == []


def test_rank_by_distance_orders_by_proximity_to_reference() -> None:
    near = _make_business(business_id=1, latitude=40.771, longitude=29.921)
    far = _make_business(business_id=2, latitude=41.5, longitude=30.5)

    result = _rank_by_distance([far, near], (40.77, 29.92), online_exempt=True)

    assert [business_id for business_id, _ in result] == [1, 2]


def test_rank_by_distance_excludes_businesses_without_coordinates() -> None:
    with_coords = _make_business(business_id=1, latitude=40.77, longitude=29.92)
    without_coords = _make_business(business_id=2, latitude=None, longitude=None)

    result = _rank_by_distance([with_coords, without_coords], (40.77, 29.92), online_exempt=True)

    assert [business_id for business_id, _ in result] == [1]


def test_rank_by_distance_excludes_online_businesses_when_exempt() -> None:
    """Online hizmet veren işletme, kullanıcı özellikle online_only istemediği
    sürece mesafeye göre cezalandırılıp ödüllendirilmemeli — bu yüzden
    online_exempt=True iken mesafe sıralamasından tamamen çıkarılır."""
    physical = _make_business(business_id=1, latitude=41.5, longitude=30.5, online_available=False)
    online = _make_business(business_id=2, latitude=40.77, longitude=29.92, online_available=True)

    result = _rank_by_distance([physical, online], (40.77, 29.92), online_exempt=True)

    assert [business_id for business_id, _ in result] == [1]


def test_rank_by_distance_includes_online_businesses_when_not_exempt() -> None:
    """Kullanıcı online_only=True gibi mesafeyi bilerek istediğinde
    (online_exempt=False), online işletmeler de normal şekilde sıralanır."""
    physical = _make_business(business_id=1, latitude=41.5, longitude=30.5, online_available=False)
    online = _make_business(business_id=2, latitude=40.77, longitude=29.92, online_available=True)

    result = _rank_by_distance([physical, online], (40.77, 29.92), online_exempt=False)

    assert [business_id for business_id, _ in result] == [2, 1]


def test_apply_final_sort_returns_original_order_without_any_signal() -> None:
    businesses = [_make_business(business_id=1), _make_business(business_id=2)]

    result = apply_final_sort(businesses, rating_preference=None, distance_reference=None)

    assert [b.id for b in result] == [1, 2]


def test_apply_final_sort_reduces_to_rating_only_behavior_when_alone() -> None:
    """Tek sinyal (sadece rating) verildiğinde RRF, mevcut _rank_by_rating
    sırasını aynen korumalı — puansızlar dahil, hiçbiri sonuçtan düşmemeli."""
    rated_low = _make_business(business_id=1, weighted_rating=3.0)
    rated_high = _make_business(business_id=2, weighted_rating=4.8)
    unrated = _make_business(business_id=3, weighted_rating=None)

    result = apply_final_sort([rated_low, unrated, rated_high], rating_preference="high", distance_reference=None)

    assert [b.id for b in result] == [2, 1, 3]


def test_apply_final_sort_combines_rating_and_distance_via_rrf() -> None:
    """En yakın ama düşük puanlı ile uzak ama yüksek puanlı işletme
    arasında, ikisi de aktifken RRF ikisini de dengeleyerek sıralamalı —
    tekil sinyallerin tersini üretmemeli (ikisi de dahil edilmeli)."""
    close_low_rated = _make_business(business_id=1, latitude=40.771, longitude=29.921, weighted_rating=3.0)
    far_high_rated = _make_business(business_id=2, latitude=41.5, longitude=30.5, weighted_rating=4.9)

    result = apply_final_sort(
        [close_low_rated, far_high_rated], rating_preference="high", distance_reference=(40.77, 29.92)
    )

    assert {b.id for b in result} == {1, 2}


def test_apply_final_sort_appends_businesses_excluded_from_every_signal() -> None:
    """Hiçbir sinyale dahil olmayan (konumu yok VE puansız) bir işletme
    sonuçtan düşmemeli, en sona eklenmeli."""
    rated_with_coords = _make_business(business_id=1, latitude=40.77, longitude=29.92, weighted_rating=4.0)
    neither = _make_business(business_id=2, latitude=None, longitude=None, weighted_rating=None)

    result = apply_final_sort(
        [neither, rated_with_coords], rating_preference="high", distance_reference=(40.77, 29.92)
    )

    assert [b.id for b in result] == [1, 2]


class _FakeEmbeddingProvider:
    name = "fake"
    dimension = 3

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _IdentityRerankerProvider:
    """Sırayı değiştirmeden döner — bu testler reranking mantığını değil,
    RRF/filtre/sayfalama davranışını doğruluyor (reranker'ın kendi testleri
    test_reranker.py'de ayrıca var)."""

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        return [(i, 1.0) for i in range(len(documents))]

    async def close(self) -> None:
        pass


def _make_session_returning(businesses: list[Business]) -> AsyncMock:
    session = AsyncMock()
    scalars_result = SimpleNamespace(all=lambda: businesses)
    session.execute.return_value = SimpleNamespace(scalars=lambda: scalars_result)
    return session


async def test_search_providers_skips_filtered_id_fetch_when_no_filters(monkeypatch) -> None:
    fetch_filtered_called = False

    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9)]

    async def fake_fetch_filtered_business_ids(*args, **kwargs):
        nonlocal fetch_filtered_called
        fetch_filtered_called = True
        return set()

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)
    monkeypatch.setattr(
        "backend.services.search.service.fetch_filtered_business_ids", fake_fetch_filtered_business_ids
    )

    business = _make_business(business_id=1)
    session = _make_session_returning([business])
    bm25_index = _build_bm25_index(
        [
            business,
            _make_business(business_id=10, title="Kuaför Salonu", rich_description="Saç kesimi hizmeti."),
            _make_business(business_id=11, title="Oto Yıkama", rich_description="Araç yıkama servisi."),
        ]
    )

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=bm25_index,
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
    )

    assert fetch_filtered_called is False
    # total artık DB'den gerçekten çekilen işletme sayısı (BM25/RRF top_k
    # içinde 3 aday olsa da — >0 skor filtresi bilerek yok, bkz. bm25.py
    # "DİKKAT" notu — mock session sadece business 1'i "var" sayıyor).
    # Asıl doğruluk sinyali business 1'in en alakalı olarak en üstte
    # sıralanması.
    assert response.total == 1
    assert response.results[0].id == 1


async def test_search_providers_intersects_bm25_with_filtered_ids_when_filters_present(monkeypatch) -> None:
    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9)]

    async def fake_fetch_filtered_business_ids(*args, **kwargs):
        return {1}  # sadece business 1 filtreyi sağlıyor

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)
    monkeypatch.setattr(
        "backend.services.search.service.fetch_filtered_business_ids", fake_fetch_filtered_business_ids
    )

    business_1 = _make_business(business_id=1, title="Kuaför Alfa", rich_description="Saç kesim salonu.")
    business_2 = _make_business(
        business_id=2,
        title="Diş Kliniği Beta",
        services=["kanal tedavisi"],
        rich_description="Diş ağrısı ve kanal tedavisi uzmanı diş hekimi.",
        keywords=["diş kanal"],
    )
    session = _make_session_returning([business_1, business_2])
    # business_2, "diş" sorgusunda BM25'te açıkça business_1'den üstte
    # sıralanır (3. bir işletme de N=2 IDF dejenerasyonunu kırmak için var,
    # bkz. test_bm25.py'deki aynı not) — ama filtre sadece 1'i geçiriyor,
    # bu yüzden 2 sonuçtan düşmeli.
    bm25_index = _build_bm25_index(
        [business_1, business_2, _make_business(business_id=12, title="Oto Yıkama Gama", rich_description="Araç yıkama servisi.")]
    )

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=bm25_index,
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(gender="unisex"),
    )

    result_ids = {result.id for result in response.results}
    assert 2 not in result_ids


async def test_search_providers_applies_limit_and_offset(monkeypatch) -> None:
    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8), (3, 0.7)]

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)

    businesses = [_make_business(business_id=i) for i in (1, 2, 3)]
    session = _make_session_returning(businesses)

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),  # hiç build() çağrılmadı, .search() her zaman [] döner
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
        limit=1,
        offset=1,
    )

    assert response.total == 3
    assert len(response.results) == 1


async def test_search_providers_filters_out_unavailable_businesses_when_availability_given(monkeypatch) -> None:
    """İki fazlı müsaitlik kontrolünün ikinci fazı: RRF sonrası aday
    havuzundan, verilen tarihte/saatte müsait olmayan işletmeler elenir
    (bkz. availability.py docstring'i)."""

    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8)]

    async def fake_fetch_available_business_ids(*args, **kwargs):
        return {1}  # sadece business 1 müsait

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)
    monkeypatch.setattr(
        "backend.services.search.service.fetch_available_business_ids", fake_fetch_available_business_ids
    )

    businesses = [_make_business(business_id=1), _make_business(business_id=2)]
    session = _make_session_returning(businesses)

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
        availability=DateAvailabilityFilter(date=date(2026, 8, 12)),
    )

    result_ids = {result.id for result in response.results}
    assert result_ids == {1}


async def test_search_providers_sorts_by_rating_preference_after_reranking(monkeypatch) -> None:
    """rating_preference verildiğinde, reranker'ın alaka sırasını değil
    weighted_rating sırasını görmeliyiz (ADR-0015) — reranker burada bilerek
    RRF/vektör sırasını (1, 2, 3) korur, ama en düşük puanlı business_id=3
    "low" tercihiyle en üste çıkmalı."""

    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8), (3, 0.7)]

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)

    businesses = [
        _make_business(business_id=1, weighted_rating=4.8),
        _make_business(business_id=2, weighted_rating=4.5),
        _make_business(business_id=3, weighted_rating=2.1),
    ]
    session = _make_session_returning(businesses)

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
        rating_preference="low",
    )

    assert [result.id for result in response.results] == [3, 2, 1]


async def test_search_providers_sorts_by_distance_reference_after_reranking(monkeypatch) -> None:
    """distance_reference verildiğinde reranker sırası değil mesafeye
    yakınlık sırası görülmeli, sonuçlarda distance_km de dolu olmalı."""

    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8)]

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)

    far = _make_business(business_id=1, latitude=41.5, longitude=30.5)
    near = _make_business(business_id=2, latitude=40.771, longitude=29.921)
    session = _make_session_returning([far, near])

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
        distance_reference=(40.77, 29.92),
    )

    assert [result.id for result in response.results] == [2, 1]
    assert response.results[0].distance_km is not None


async def test_search_providers_includes_online_businesses_in_distance_sort_when_online_only_requested(
    monkeypatch,
) -> None:
    """online_only=True açıkça istendiğinde, online işletmeler artık mesafe
    sıralamasından muaf tutulmamalı (bkz. apply_final_sort docstring'i) —
    filters.online_only, apply_final_sort'un online_exempt_from_distance'ına
    doğru şekilde ulaşmalı."""

    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8)]

    async def fake_fetch_filtered_business_ids(*args, **kwargs):
        return {1, 2}

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)
    monkeypatch.setattr(
        "backend.services.search.service.fetch_filtered_business_ids", fake_fetch_filtered_business_ids
    )

    far_physical = _make_business(business_id=1, latitude=41.5, longitude=30.5, online_available=False)
    near_online = _make_business(business_id=2, latitude=40.771, longitude=29.921, online_available=True)
    session = _make_session_returning([far_physical, near_online])

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(online_only=True),
        distance_reference=(40.77, 29.92),
    )

    assert [result.id for result in response.results] == [2, 1]


async def test_search_providers_keeps_rerank_order_when_no_rating_preference(monkeypatch) -> None:
    async def fake_vector_search(*args, **kwargs):
        return [(1, 0.9), (2, 0.8), (3, 0.7)]

    monkeypatch.setattr("backend.services.search.service.vector_search", fake_vector_search)

    businesses = [
        _make_business(business_id=1, weighted_rating=4.8),
        _make_business(business_id=2, weighted_rating=4.5),
        _make_business(business_id=3, weighted_rating=2.1),
    ]
    session = _make_session_returning(businesses)

    response = await search_providers(
        session=session,
        qdrant_client=AsyncMock(),
        bm25_index=BM25Index(),
        embedding_provider=_FakeEmbeddingProvider(),
        reranker_provider=_IdentityRerankerProvider(),
        query="diş",
        filters=SearchFilters(),
    )

    assert [result.id for result in response.results] == [1, 2, 3]

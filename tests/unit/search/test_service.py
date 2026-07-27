"""backend/services/search/service.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.db.models import Business
from backend.services.search.bm25 import BM25Index
from backend.services.search.filters import NearFilter, SearchFilters
from backend.services.search.service import _to_provider_result, search_providers


def _make_business(
    business_id: int = 1,
    title: str = "Test Diş Kliniği",
    services: list[str] | None = None,
    rich_description: str = "Açıklama",
    keywords: list[str] | None = None,
    latitude: float | None = 40.77,
    longitude: float | None = 29.92,
) -> Business:
    return Business(
        id=business_id,
        title=title,
        type_normalized="Diş Kliniği",
        rating=4.5,
        weighted_rating=4.3,
        price_min=100,
        price_max=300,
        address="İzmit",
        phone="0000",
        online_available=False,
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


def test_to_provider_result_computes_distance_when_near_filter_given() -> None:
    business = _make_business(latitude=40.77, longitude=29.92)
    near = NearFilter(latitude=40.78, longitude=29.93, radius_km=5)

    result = _to_provider_result(business, near)

    assert result.distance_km is not None
    assert result.distance_km > 0


def test_to_provider_result_leaves_distance_none_without_near_filter() -> None:
    business = _make_business()

    result = _to_provider_result(business, None)

    assert result.distance_km is None


def test_to_provider_result_leaves_distance_none_when_business_has_no_coordinates() -> None:
    business = _make_business(latitude=None, longitude=None)
    near = NearFilter(latitude=40.78, longitude=29.93, radius_km=5)

    result = _to_provider_result(business, near)

    assert result.distance_km is None


class _FakeEmbeddingProvider:
    name = "fake"
    dimension = 3

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


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
        query="diş",
        filters=SearchFilters(),
    )

    assert fetch_filtered_called is False
    # total=3: BM25 top_k içinde tüm corpus'u döner (>0 skor filtresi
    # bilerek yok, bkz. bm25.py "DİKKAT" notu) — asıl doğruluk sinyali
    # business 1'in en alakalı olarak en üstte sıralanması.
    assert response.total == 3
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
        query="diş",
        filters=SearchFilters(),
        limit=1,
        offset=1,
    )

    assert response.total == 3
    assert len(response.results) == 1

"""backend/services/search/vector.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from qdrant_client.models import FieldCondition, Filter, MatchValue

from backend.services.search.vector import _build_active_only_filter, fetch_filtered_business_ids, vector_search


class _FakeEmbeddingProvider:
    """embed_batch çağrısını gerçek OpenAI'ye gitmeden taklit eden test double'ı."""

    name = "fake"
    dimension = 3

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


async def test_vector_search_returns_business_id_score_pairs() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(id=7, score=0.87), SimpleNamespace(id=3, score=0.65)]
    )

    results = await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    assert results == [(7, 0.87), (3, 0.65)]


async def test_vector_search_always_applies_is_active_filter() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[])

    await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    applied_filter = fake_client.query_points.call_args.kwargs["query_filter"]
    condition_keys = [condition.key for condition in applied_filter.must]
    assert "is_active" in condition_keys


async def test_vector_search_uses_provider_specific_collection_name() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[])

    await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    assert fake_client.query_points.call_args.kwargs["collection_name"] == "businesses_fake"


def _condition_keys(must: object) -> set[str]:
    """`Filter.must` `Condition | list[Condition] | None` union tipinde —
    bu yardımcı, test'lerde her zaman FieldCondition listesi döndüğünü
    (gerçek isinstance kontrolüyle) doğrulayıp sade bir key kümesine çevirir."""
    assert isinstance(must, list)
    keys: set[str] = set()
    for condition in must:
        assert isinstance(condition, FieldCondition)
        keys.add(condition.key)
    return keys


def test_build_active_only_filter_returns_only_is_active_when_no_extra_filter() -> None:
    result = _build_active_only_filter(None)

    assert _condition_keys(result.must) == {"is_active"}


def test_build_active_only_filter_extends_with_list_extra_filter() -> None:
    extra_filter = Filter(
        must=[
            FieldCondition(key="gender", match=MatchValue(value="unisex")),
            FieldCondition(key="online_available", match=MatchValue(value=True)),
        ]
    )

    result = _build_active_only_filter(extra_filter)

    assert _condition_keys(result.must) == {"is_active", "gender", "online_available"}


def test_build_active_only_filter_appends_single_condition_extra_filter() -> None:
    """extra_filter.must tekil bir Condition (liste değil) olduğunda da
    doğru birleşmeli — .extend() yerine .append() dallanması (bkz. vector.py
    docstring'indeki uyarı: sadece liste varsayıp .extend() çağırmak, tekil
    bir Condition geldiğinde sessizce yanlış davranırdı)."""
    single_condition = FieldCondition(key="gender", match=MatchValue(value="unisex"))
    extra_filter = Filter(must=single_condition)

    result = _build_active_only_filter(extra_filter)

    assert _condition_keys(result.must) == {"is_active", "gender"}


async def test_fetch_filtered_business_ids_returns_ids_from_single_page() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.scroll.return_value = ([SimpleNamespace(id=1), SimpleNamespace(id=2)], None)

    result = await fetch_filtered_business_ids(fake_client, provider, None)

    assert result == {1, 2}
    fake_client.scroll.assert_awaited_once()


async def test_fetch_filtered_business_ids_paginates_until_offset_is_none() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.scroll.side_effect = [
        ([SimpleNamespace(id=1)], "sonraki-sayfa-token"),
        ([SimpleNamespace(id=2)], None),
    ]

    result = await fetch_filtered_business_ids(fake_client, provider, None)

    assert result == {1, 2}
    assert fake_client.scroll.call_count == 2

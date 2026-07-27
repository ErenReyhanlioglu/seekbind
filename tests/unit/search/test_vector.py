"""backend/services/search/vector.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.search.vector import vector_search


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

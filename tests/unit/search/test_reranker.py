"""backend/services/search/reranker.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services.search.reranker import (
    JinaReranker,
    RerankerServiceError,
    get_reranker_provider,
)


def _make_response(payload: dict, status_code: int = 200) -> SimpleNamespace:
    def raise_for_status() -> None:
        if status_code >= 400:
            raise httpx.HTTPStatusError("hata", request=None, response=None)  # type: ignore[arg-type]

    return SimpleNamespace(json=lambda: payload, raise_for_status=raise_for_status)


async def test_rerank_returns_index_score_pairs_from_response() -> None:
    reranker = JinaReranker()
    reranker._client.post = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_response(
            {
                "model": "jina-reranker-v3",
                "usage": {"total_tokens": 42},
                "results": [
                    {"index": 1, "relevance_score": 0.93},
                    {"index": 0, "relevance_score": 0.81},
                ],
            }
        )
    )

    results = await reranker.rerank("diş kliniği", ["metin a", "metin b"], top_n=2)

    assert results == [(1, 0.93), (0, 0.81)]


async def test_rerank_sends_correct_request_body() -> None:
    reranker = JinaReranker()
    reranker._client.post = AsyncMock(  # type: ignore[method-assign]
        return_value=_make_response({"results": []})
    )

    await reranker.rerank("diş kliniği", ["metin a"], top_n=5)

    call = reranker._client.post.call_args
    assert call.args[0] == "https://api.jina.ai/v1/rerank"
    body = call.kwargs["json"]
    assert body["query"] == "diş kliniği"
    assert body["documents"] == ["metin a"]
    assert body["top_n"] == 5
    assert body["return_documents"] is False
    assert "Authorization" in call.kwargs["headers"]


async def test_rerank_returns_empty_list_for_empty_documents_without_http_call() -> (
    None
):
    reranker = JinaReranker()
    reranker._client.post = AsyncMock()  # type: ignore[method-assign]

    results = await reranker.rerank("diş kliniği", [], top_n=5)

    assert results == []
    reranker._client.post.assert_not_called()


async def test_rerank_raises_service_error_on_timeout() -> None:
    reranker = JinaReranker()
    reranker._client.post = AsyncMock(side_effect=httpx.TimeoutException("zaman aşımı"))  # type: ignore[method-assign]

    with pytest.raises(RerankerServiceError):
        await reranker.rerank("diş kliniği", ["metin a"], top_n=5)


async def test_rerank_raises_service_error_on_http_status_error() -> None:
    reranker = JinaReranker()
    reranker._client.post = AsyncMock(return_value=_make_response({}, status_code=500))  # type: ignore[method-assign]

    with pytest.raises(RerankerServiceError):
        await reranker.rerank("diş kliniği", ["metin a"], top_n=5)


async def test_close_closes_underlying_http_client() -> None:
    reranker = JinaReranker()
    reranker._client.aclose = AsyncMock()  # type: ignore[method-assign]

    await reranker.close()

    reranker._client.aclose.assert_awaited_once()


def test_get_reranker_provider_returns_jina_reranker_instance() -> None:
    get_reranker_provider.cache_clear()

    try:
        provider = get_reranker_provider()
        assert isinstance(provider, JinaReranker)
    finally:
        get_reranker_provider.cache_clear()


def test_get_reranker_provider_returns_same_instance_on_repeated_calls() -> None:
    get_reranker_provider.cache_clear()

    try:
        assert get_reranker_provider() is get_reranker_provider()
    finally:
        get_reranker_provider.cache_clear()

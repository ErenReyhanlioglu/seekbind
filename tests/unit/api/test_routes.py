"""backend/api/routes.py için birim testler."""

from datetime import date
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

import backend.api.routes as routes_module
from backend.api.schemas import BookRequest, BookResponse, DependencyStatus, RecommendationResponse, RecommendRequest
from backend.api.routes import book, check_llm_config, check_postgres, check_qdrant, health_check, recommend
from backend.services.calendar import SlotNotFoundError
from backend.services.embedding import EmbeddingProvider
from backend.services.llm import LLMProvider
from backend.services.search import BM25Index, RerankerProvider

# Bu testlerde search_providers/get_recommendation monkeypatch'le değiştiriliyor,
# yani bu bağımlılıklar gerçekte hiç kullanılmıyor — cast() ile Pyright'a
# "biliyorum, gerçek tip değil ama önemli değil" deniyor (rag/test_service.py'deki
# aynı desen).
_BM25_INDEX = cast(BM25Index, object())
_EMBEDDING_PROVIDER = cast(EmbeddingProvider, object())
_RERANKER_PROVIDER = cast(RerankerProvider, object())
_LLM_PROVIDER = cast(LLMProvider, object())


async def test_check_postgres_returns_healthy_when_query_succeeds() -> None:
    session = AsyncMock()

    result = await check_postgres(session)

    assert result.name == "postgres"
    assert result.healthy is True
    assert result.detail is None


async def test_check_postgres_returns_unhealthy_with_detail_when_query_fails() -> None:
    session = AsyncMock()
    session.execute.side_effect = ConnectionError("bağlantı koptu")

    result = await check_postgres(session)

    assert result.healthy is False
    assert result.detail is not None
    assert "bağlantı koptu" in result.detail


async def test_check_qdrant_returns_healthy_when_request_succeeds() -> None:
    client = AsyncMock()

    result = await check_qdrant(client)

    assert result.name == "qdrant"
    assert result.healthy is True


async def test_check_qdrant_returns_unhealthy_with_detail_when_request_fails() -> None:
    client = AsyncMock()
    client.get_collections.side_effect = ConnectionError("qdrant'a ulaşılamadı")

    result = await check_qdrant(client)

    assert result.healthy is False
    assert result.detail is not None
    assert "qdrant'a ulaşılamadı" in result.detail


def test_check_llm_config_healthy_when_api_key_configured(monkeypatch) -> None:
    fake_settings = MagicMock(openai_api_key=SecretStr("sk-test"))
    monkeypatch.setattr(routes_module, "get_settings", lambda: fake_settings)

    result = check_llm_config()

    assert result.healthy is True
    assert result.detail is None


def test_check_llm_config_unhealthy_when_api_key_missing(monkeypatch) -> None:
    fake_settings = MagicMock(openai_api_key=SecretStr(""))
    monkeypatch.setattr(routes_module, "get_settings", lambda: fake_settings)

    result = check_llm_config()

    assert result.healthy is False
    assert result.detail is not None


async def test_health_check_returns_healthy_when_all_dependencies_healthy(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_module, "check_postgres", AsyncMock(return_value=DependencyStatus(name="postgres", healthy=True))
    )
    monkeypatch.setattr(
        routes_module, "check_qdrant", AsyncMock(return_value=DependencyStatus(name="qdrant", healthy=True))
    )
    monkeypatch.setattr(
        routes_module, "check_llm_config", MagicMock(return_value=DependencyStatus(name="llm_config", healthy=True))
    )

    response = await health_check(session=AsyncMock(), qdrant_client=AsyncMock())

    assert response.status == "healthy"
    assert len(response.dependencies) == 3


async def test_health_check_returns_unhealthy_when_any_dependency_unhealthy(monkeypatch) -> None:
    """Tek bir bağımlılık bile unhealthy olsa genel durum unhealthy olmalı —
    orkestrasyon araçları (Docker/Kubernetes) bu genel duruma göre karar
    veriyor (bkz. CLAUDE.md 'derin health check' kuralı)."""
    monkeypatch.setattr(
        routes_module,
        "check_postgres",
        AsyncMock(return_value=DependencyStatus(name="postgres", healthy=False, detail="hata")),
    )
    monkeypatch.setattr(
        routes_module, "check_qdrant", AsyncMock(return_value=DependencyStatus(name="qdrant", healthy=True))
    )
    monkeypatch.setattr(
        routes_module, "check_llm_config", MagicMock(return_value=DependencyStatus(name="llm_config", healthy=True))
    )

    response = await health_check(session=AsyncMock(), qdrant_client=AsyncMock())

    assert response.status == "unhealthy"


async def test_recommend_calls_get_recommendation_with_request_fields(monkeypatch) -> None:
    captured: dict = {}

    async def fake_get_recommendation(**kwargs):
        captured.update(kwargs)
        return RecommendationResponse(recommendation="test önerisi", results=[], total=0)

    monkeypatch.setattr(routes_module, "get_recommendation", fake_get_recommendation)
    request = RecommendRequest(query="ucuz dişçi", limit=5, offset=2)

    response = await recommend(
        request=request,
        session=cast(AsyncSession, object()),
        qdrant_client=cast(AsyncQdrantClient, object()),
        bm25_index=_BM25_INDEX,
        embedding_provider=_EMBEDDING_PROVIDER,
        reranker_provider=_RERANKER_PROVIDER,
        llm_provider=_LLM_PROVIDER,
    )

    assert captured["raw_query"] == "ucuz dişçi"
    assert captured["limit"] == 5
    assert captured["offset"] == 2
    assert isinstance(captured["today"], date)
    assert response.recommendation == "test önerisi"


async def test_book_calls_book_appointment_with_request_fields(monkeypatch) -> None:
    captured: dict = {}

    async def fake_book_appointment(
        session, user_id, appointment_slot_id, *, online_only=False, gender=None, min_price=None, max_price=None
    ):
        captured.update(
            user_id=user_id,
            appointment_slot_id=appointment_slot_id,
            online_only=online_only,
            gender=gender,
            min_price=min_price,
            max_price=max_price,
        )
        return BookResponse(success=True, booking_id=42)

    monkeypatch.setattr(routes_module, "book_appointment", fake_book_appointment)
    request = BookRequest(user_id=1, appointment_slot_id=7, online_only=True, gender="unisex", max_price=500)

    response = await book(request=request, session=cast(AsyncSession, object()))

    assert captured == {
        "user_id": 1,
        "appointment_slot_id": 7,
        "online_only": True,
        "gender": "unisex",
        "min_price": None,
        "max_price": 500,
    }
    assert response.success is True
    assert response.booking_id == 42


async def test_book_raises_http_404_when_slot_not_found(monkeypatch) -> None:
    async def fake_book_appointment(
        session, user_id, appointment_slot_id, *, online_only=False, gender=None, min_price=None, max_price=None
    ):
        raise SlotNotFoundError(f"appointment_slot_id={appointment_slot_id} bulunamadı")

    monkeypatch.setattr(routes_module, "book_appointment", fake_book_appointment)
    request = BookRequest(user_id=1, appointment_slot_id=999)

    with pytest.raises(HTTPException) as exc_info:
        await book(request=request, session=cast(AsyncSession, object()))

    assert exc_info.value.status_code == 404

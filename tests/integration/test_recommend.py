"""`/recommend` için gerçek HTTP entegrasyon testleri.

Gerçek dev Postgres + Qdrant'a karşı çalışır (salt okuma, hiçbir DB
override'ı yok) — sadece LLM/embedding/reranker sahte (para/determinizm,
bkz. `conftest.py::install_fake_recommend_providers`). Amaç iş mantığını
yeniden kanıtlamak değil (bu zaten `tests/unit/rag/` ve
`scripts/diagnostics/smoke_test_rag.py`'de yapılıyor) — routing/`Depends()`/
gerçek Pydantic response şemasının uçtan uca çalıştığını kanıtlamak.

Dev veri zamanla değişebileceği için assertion'lar exact-value değil
structural (200 mü, şemaya uyuyor mu, sonuç boş/dolu mu) tutuluyor.
"""

from collections.abc import Callable

import httpx
import pytest

from backend.api.schemas import RecommendationResponse
from backend.services.rag.service import EMPTY_RESULTS_MESSAGE

pytestmark = pytest.mark.integration

_GENERIC_INTENT_JSON = '{"semantic_query": "randevu"}'
_DENTIST_PRICE_INTENT_JSON = (
    '{"semantic_query": "dişçi", "category": "Diş Kliniği", "price_preference": "cheap"}'
)
_IMPOSSIBLE_PRICE_INTENT_JSON = '{"semantic_query": "berber", "min_price": 999999999}'
_NEAR_ME_DENTIST_INTENT_JSON = '{"semantic_query": "dişçi", "category": "Diş Kliniği", "near_me": true}'


async def test_recommend_returns_structural_response_for_generic_query(
    api_client: httpx.AsyncClient, install_fake_recommend_providers: Callable[[str, str], None]
) -> None:
    install_fake_recommend_providers(_GENERIC_INTENT_JSON, "İşte size uygun birkaç öneri.")

    response = await api_client.post("/recommend", json={"query": "bana bir yer öner", "user_id": 1})

    assert response.status_code == 200
    body = RecommendationResponse.model_validate(response.json())
    assert body.recommendation
    assert len(body.results) > 0
    assert body.total > 0


async def test_recommend_resolves_price_threshold_from_real_db(
    api_client: httpx.AsyncClient, install_fake_recommend_providers: Callable[[str, str], None]
) -> None:
    """Sahte LLM'in `price_preference` sinyali, `resolve_price_threshold()`
    üzerinden gerçek bir DB sorgusunu (percentile hesabı) tetikliyor —
    fake LLM'i sadece en az test edilmiş (filtresiz) yoldan geçirmemek için."""
    install_fake_recommend_providers(_DENTIST_PRICE_INTENT_JSON, "Uygun fiyatlı bir diş kliniği buldum.")

    response = await api_client.post("/recommend", json={"query": "ucuz dişçi", "user_id": 1})

    assert response.status_code == 200
    body = RecommendationResponse.model_validate(response.json())
    assert len(body.results) > 0
    assert all(result.type_normalized == "Diş Kliniği" for result in body.results)


async def test_recommend_returns_empty_results_message_for_impossible_price_range(
    api_client: httpx.AsyncClient, install_fake_recommend_providers: Callable[[str, str], None]
) -> None:
    """Sonuç bulunamayan bir filtre kombinasyonu istisna değil, normal bir
    200 yanıtı üretmeli (bkz. `rag/service.py::EMPTY_RESULTS_MESSAGE`)."""
    install_fake_recommend_providers(_IMPOSSIBLE_PRICE_INTENT_JSON, "Bu metin hiç kullanılmamalı.")

    response = await api_client.post("/recommend", json={"query": "berber", "user_id": 1})

    assert response.status_code == 200
    body = RecommendationResponse.model_validate(response.json())
    assert body.results == []
    assert body.total == 0
    assert body.recommendation == EMPTY_RESULTS_MESSAGE


async def test_recommend_near_me_populates_distance_km_using_real_user_location(
    api_client: httpx.AsyncClient,
    install_fake_recommend_providers: Callable[[str, str], None],
    real_test_user_id: int,
) -> None:
    """`near_me=true`, gerçek `UserProfile` koordinatları üzerinden
    `distance_km` alanını gerçekten HTTP yanıtına kadar dolduruyor mu."""
    install_fake_recommend_providers(_NEAR_ME_DENTIST_INTENT_JSON, "Size en yakın diş kliniklerini listeledim.")

    response = await api_client.post("/recommend", json={"query": "yakınımda bir dişçi", "user_id": real_test_user_id})

    assert response.status_code == 200
    body = RecommendationResponse.model_validate(response.json())
    assert len(body.results) > 0
    assert all(result.distance_km is not None for result in body.results)

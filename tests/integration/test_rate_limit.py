"""Rate limiting middleware için gerçek HTTP entegrasyon testleri.

`api_client`'ın paylaştığı `127.0.0.1` IP sepetini kirletmemek için kendi
izole `httpx.AsyncClient`'ını farklı bir sahte istemci IP'siyle kuruyor —
bkz. conftest.py::api_client (ASGITransport varsayılan olarak 127.0.0.1
kullanır, diğer tüm entegrasyon testleri bunu paylaşıyor).
"""

from collections.abc import AsyncGenerator

import httpx
import pytest

import backend.middleware.rate_limit as rate_limit_module
from backend.config import get_settings
from backend.main import app

pytestmark = pytest.mark.integration

_ISOLATED_CLIENT_IP: tuple[str, int] = ("203.0.113.1", 12345)
_TEST_RATE_LIMIT: int = 3


@pytest.fixture
async def isolated_client(
    api_client: httpx.AsyncClient,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """`api_client`'ı sadece `lifespan()`'ın zaten aktif olduğundan emin olmak
    için fixture bağımlılığı olarak alıyor — `lifespan()`'ı ikinci kez
    girmiyor, sadece kendi izole IP'sine sahip ayrı bir transport kuruyor."""
    transport = httpx.ASGITransport(app=app, client=_ISOLATED_CLIENT_IP)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def low_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """`rate_limit_per_minute`'u teste özgü düşük bir değere indirir —
    gerçek prod limitine (60) ulaşmak için onlarca gerçek istek atmak yerine."""
    real_settings = get_settings()
    fake_settings = real_settings.model_copy(
        update={"rate_limit_per_minute": _TEST_RATE_LIMIT}
    )
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: fake_settings)


async def test_requests_under_limit_succeed(
    isolated_client: httpx.AsyncClient, low_rate_limit: None
) -> None:
    for _ in range(_TEST_RATE_LIMIT):
        response = await isolated_client.get("/health")
        assert response.status_code == 200


async def test_request_over_limit_returns_429_with_retry_after_header(
    isolated_client: httpx.AsyncClient, low_rate_limit: None
) -> None:
    for _ in range(_TEST_RATE_LIMIT):
        await isolated_client.get("/health")

    response = await isolated_client.get("/health")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"

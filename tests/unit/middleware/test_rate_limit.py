"""backend/middleware/rate_limit.py için birim testler."""

import pytest
from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import Response

import backend.middleware.rate_limit as rate_limit_module
from backend.middleware.rate_limit import RateLimitMiddleware

_ASGI_VERSION: dict[str, str] = {"version": "3.0"}


def _make_request(client_host: str | None = "1.2.3.4") -> Request:
    """Ham bir ASGI scope'tan `Request` kuruyor — tam bir `TestClient` gerekmiyor."""
    scope: dict[str, object] = {
        "type": "http",
        "asgi": _ASGI_VERSION,
        "http_version": "1.1",
        "method": "GET",
        "path": "/health",
        "headers": [],
        "client": (client_host, 12345) if client_host is not None else None,
    }
    return Request(scope)


async def _call_next(request: Request) -> Response:
    return Response("ok", status_code=200)


class _FakeRedis:
    """Bellek-içi, sabit pencereli `incr`/`expire` taklidi.

    `test_cache.py`'nin kendi `_FakeRedis`'inden bilinçli olarak ayrı — bu
    repoda her test dosyası kendi yerel sahtesini tanımlıyor.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self._counters: dict[str, int] = {}
        self._fail = fail
        self.expire_calls: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        if self._fail:
            raise RedisError("bağlantı hatası")
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def expire(self, key: str, seconds: int, nx: bool = False) -> bool:
        if self._fail:
            raise RedisError("bağlantı hatası")
        self.expire_calls.append((key, seconds))
        return True


class _FakeSettings:
    def __init__(self, rate_limit_per_minute: int) -> None:
        self.rate_limit_per_minute = rate_limit_per_minute


def _patch(monkeypatch: pytest.MonkeyPatch, redis: _FakeRedis, limit: int) -> None:
    monkeypatch.setattr(rate_limit_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(rate_limit_module, "get_settings", lambda: _FakeSettings(rate_limit_per_minute=limit))


async def test_dispatch_allows_requests_under_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedis()
    _patch(monkeypatch, redis, limit=3)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]

    response = await middleware.dispatch(_make_request(), _call_next)

    assert response.status_code == 200


async def test_dispatch_returns_429_once_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedis()
    _patch(monkeypatch, redis, limit=2)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]
    request = _make_request()

    await middleware.dispatch(request, _call_next)
    await middleware.dispatch(request, _call_next)
    response = await middleware.dispatch(request, _call_next)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


async def test_dispatch_fails_open_when_redis_incr_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis'e ulaşılamazsa istek reddedilmemeli — bkz. cache.py'deki aynı felsefe."""
    redis = _FakeRedis(fail=True)
    _patch(monkeypatch, redis, limit=1)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]

    response = await middleware.dispatch(_make_request(), _call_next)

    assert response.status_code == 200


async def test_dispatch_uses_separate_buckets_per_client_host(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = _FakeRedis()
    _patch(monkeypatch, redis, limit=1)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]

    first_client_response = await middleware.dispatch(_make_request("1.2.3.4"), _call_next)
    second_client_response = await middleware.dispatch(_make_request("5.6.7.8"), _call_next)

    assert first_client_response.status_code == 200
    assert second_client_response.status_code == 200


async def test_dispatch_falls_back_to_unknown_client_id_when_scope_has_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()
    _patch(monkeypatch, redis, limit=3)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]

    response = await middleware.dispatch(_make_request(client_host=None), _call_next)

    assert response.status_code == 200


async def test_dispatch_reads_settings_freshly_on_every_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """`get_settings()` her `dispatch()` çağrısında yeniden okunuyor — bu,
    entegrasyon testinin limiti geçici olarak düşürüp bir sonraki istekte
    hemen etkili olduğunu doğrulayabilmesinin dayanağı."""
    redis = _FakeRedis()
    _patch(monkeypatch, redis, limit=100)
    middleware = RateLimitMiddleware(app=None)  # type: ignore[arg-type]
    request = _make_request()

    allowed_response = await middleware.dispatch(request, _call_next)
    _patch(monkeypatch, redis, limit=1)
    blocked_response = await middleware.dispatch(request, _call_next)

    assert allowed_response.status_code == 200
    assert blocked_response.status_code == 429

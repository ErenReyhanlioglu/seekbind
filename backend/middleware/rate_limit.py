"""Sabit pencereli (fixed-window), Redis destekli IP bazlı rate limiting.

Gerçek bir ASGI middleware (app.add_middleware() ile kayıtlı) — her
endpoint'i kapsaması gerektiği için (CLAUDE.md), tek bir servis
fonksiyonuna değil route-agnostik bir katmana ait (bkz.
prompt_injection.py'nin AKSİNE gerekçesi).

Redis'e ulaşılamazsa istek reddedilmez, sessizce (log ile) geçirilir —
bkz. backend/services/cache.py'deki aynı "fail open" felsefesi.
"""

import logging
import time

from fastapi import Request
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from backend.config import get_settings
from backend.db.redis import get_redis_client

logger = logging.getLogger(__name__)

_WINDOW_SECONDS: int = 60
_RATE_LIMIT_KEY_PREFIX: str = "ratelimit"
_UNKNOWN_CLIENT_ID: str = "unknown"
_RATE_LIMIT_EXCEEDED_MESSAGE: str = "Çok fazla istek gönderildi, lütfen bir süre sonra tekrar deneyin."


def _client_identifier(request: Request) -> str:
    """`request.client`, gerçek dağıtımda ASGI sunucusundan (uvicorn) gelir;
    None olabileceği bilinen tek durum eksik/özel bir ASGI scope'u."""
    if request.client is None:
        return _UNKNOWN_CLIENT_ID
    return request.client.host


class RateLimitMiddleware(BaseHTTPMiddleware):
    """`rate_limit_per_minute` (config.py) sınırını aşan istemcilere 429 döner."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        redis = get_redis_client()
        bucket = int(time.time() // _WINDOW_SECONDS)
        key = f"{_RATE_LIMIT_KEY_PREFIX}:{_client_identifier(request)}:{bucket}"

        try:
            count = await redis.incr(key)
            await redis.expire(key, _WINDOW_SECONDS, nx=True)
        except RedisError as e:
            logger.warning("Redis'e ulaşılamadı, rate limiting atlanıyor: %s", e)
            return await call_next(request)

        if count > settings.rate_limit_per_minute:
            logger.warning("Rate limit aşıldı")
            return JSONResponse(
                status_code=429,
                content={"detail": _RATE_LIMIT_EXCEEDED_MESSAGE},
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )
        return await call_next(request)

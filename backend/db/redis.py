"""Redis client yönetimi."""

from functools import lru_cache

from redis.asyncio import Redis

from backend.config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    """Redis client'ını önbellekten döner, tekrar oluşturmaz."""
    settings = get_settings()
    return Redis.from_url(settings.redis_url)

"""Qdrant client yönetimi."""

from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from backend.config import get_settings


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    """Qdrant client'ını önbellekten döner, tekrar oluşturmaz."""
    settings = get_settings()
    return AsyncQdrantClient(url=settings.qdrant_url)

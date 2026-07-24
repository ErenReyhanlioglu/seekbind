"""API response şemaları.

Bu dosyadaki modeller endpoint'lerin döndürdüğü sözleşmedir — asla
ORM (SQLAlchemy) nesneleri doğrudan serialize edilmez, her zaman
buradaki gibi ayrı bir response schema'sına eşlenir.
"""

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    """Tek bir dış bağımlılığın (Postgres, Qdrant, LLM config vb.) sağlık durumu."""

    name: str
    healthy: bool
    detail: str | None = None


class HealthCheckResponse(BaseModel):
    """`/health` endpoint'inin döndürdüğü genel sağlık durumu."""

    status: str
    dependencies: list[DependencyStatus]

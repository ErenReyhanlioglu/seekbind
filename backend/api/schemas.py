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


class ProviderResult(BaseModel):
    """Arama sonucunda dönen tek bir işletme kaydı."""

    id: int
    title: str
    type_normalized: str
    rating: float | None
    weighted_rating: float | None
    price_min: int
    price_max: int
    address: str | None
    phone: str | None
    online_available: bool
    gender: str
    services: list[str]
    tags: list[str]
    rich_description: str | None
    distance_km: float | None = None


class SearchResponse(BaseModel):
    """`search_providers`'ın döndürdüğü sayfalanmış sonuç kümesi.

    `total`, sınırsız bir sayım değil — hybrid retrieval sabit derinlikte
    (top-30+30, RRF sonrası top-40 havuz) çalıştığı için keşfedilen aday
    havuzunun büyüklüğüdür, veritabanındaki tüm eşleşmelerin kesin sayısı
    değil (bkz. docs/roadmap.md pagination tartışması).
    """

    results: list[ProviderResult]
    total: int

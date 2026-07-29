"""API response şemaları.

Bu dosyadaki modeller endpoint'lerin döndürdüğü sözleşmedir — asla
ORM (SQLAlchemy) nesneleri doğrudan serialize edilmez, her zaman
buradaki gibi ayrı bir response schema'sına eşlenir.
"""

from pydantic import BaseModel, Field

# search_providers()'ın aday havuzu üst sınırıyla (CANDIDATE_POOL_SIZE,
# backend/services/search/service.py) aynı olmalı — buradan import edilemiyor
# çünkü service.py zaten bu dosyadan (ProviderResult/SearchResponse için)
# import ediyor, döngüsel import olurdu. Search tarafında bu değer değişirse
# burası da elle güncellenmeli.
MAX_RECOMMEND_LIMIT: int = 40


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


class RecommendRequest(BaseModel):
    """`POST /recommend` istek gövdesi — kullanıcının serbest metin sorgusu.

    Hazır `SearchFilters`/`DateAvailabilityFilter` kabul etmiyor bilerek —
    bunlar `backend.services.rag`'de LLM ile sorgudan çıkarılıyor, istemci
    sadece ham metin gönderiyor.
    """

    query: str = Field(min_length=1, max_length=500)  # ucuz bir maliyet/kötüye kullanım sınırı
    limit: int = Field(default=10, ge=1, le=MAX_RECOMMEND_LIMIT)
    offset: int = Field(default=0, ge=0)


class RecommendationResponse(BaseModel):
    """`POST /recommend` yanıtı — doğal dil öneri + altta yatan sıralanmış sonuçlar."""

    recommendation: str
    results: list[ProviderResult]
    total: int

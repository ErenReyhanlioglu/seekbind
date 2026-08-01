"""API response şemaları.

Bu dosyadaki modeller endpoint'lerin döndürdüğü sözleşmedir — asla
ORM (SQLAlchemy) nesneleri doğrudan serialize edilmez, her zaman
buradaki gibi ayrı bir response schema'sına eşlenir.
"""

from datetime import datetime
from typing import Literal

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

    `user_id` zorunlu (opsiyonel değil) — SeekBind kişiselleştirilebilir bir
    öneri sistemi olmayı hedeflediği için aramanın kime ait olduğunu baştan
    tutarlı tutmak, ileride anonim/kayıtlı arama ayrımı gibi bir karmaşıklık
    eklemekten daha basit (bkz. feat/near-filter tartışması). Şu an tek
    kullanım yeri: `near_me` sorgu sinyali varsa, kullanıcının `UserProfile`
    referans konumu buradan bulunuyor.
    """

    query: str = Field(
        min_length=1, max_length=500
    )  # ucuz bir maliyet/kötüye kullanım sınırı
    user_id: int
    limit: int = Field(default=10, ge=1, le=MAX_RECOMMEND_LIMIT)
    offset: int = Field(default=0, ge=0)


class RecommendationResponse(BaseModel):
    """`POST /recommend` yanıtı — doğal dil öneri + altta yatan sıralanmış sonuçlar."""

    recommendation: str
    results: list[ProviderResult]
    total: int


class BookingAlternative(BaseModel):
    """`book_appointment()` başarısız olduğunda (slot dolu ya da kullanıcının
    kendi randevusuyla çakışıyor) önerilen boş bir slot — aynı işletmeden
    ya da aynı kategorideki başka bir işletmeden olabilir.

    `business`, `/recommend`'in de kullandığı `ProviderResult` — aynı
    zengin bilgi (fiyat, adres, telefon, hizmetler vb.) burada da
    tekrarlanmasın, tek bir yerden geliyor. `distance_km`, `BookRequest.near_me`
    true ise ve kullanıcının referans konumu biliniyorsa doludur, aksi halde
    `None` kalır.
    """

    business: ProviderResult
    appointment_slot_id: int
    start_time: datetime


class BookRequest(BaseModel):
    """`POST /book` istek gövdesi — belirli bir slotu belirli bir kullanıcıya rezerve etme isteği.

    `online_only`/`gender`/`min_price`/`max_price`/`near_me` opsiyonel —
    çağıran (örn. bir frontend ya da SeekBind 2.0), zaten `/recommend`'e
    yaptığı orijinal çağrıdan bu tercihleri elinde tutuyorsa, alternatif
    önerisinin de bunlara uymasını istiyorsa iletebilir. `SearchFilters`
    doğrudan gömülmüyor bilerek — `category`/`near` gibi burada anlamsız
    alanlar taşımasın diye (bkz. `RecommendRequest`'in aynı gerekçesi).
    """

    user_id: int
    appointment_slot_id: int
    online_only: bool = False
    gender: Literal["female", "male", "unisex"] | None = None
    min_price: int | None = None
    max_price: int | None = None
    near_me: bool = False


class BookResponse(BaseModel):
    """`POST /book` yanıtı.

    `success=True` ise `booking_id` dolu. `success=False` ise (slot dolu
    ya da kullanıcının başka bir randevusuyla çakışıyor) `alternatives`
    doldurulur — düz metin değil, yapılandırılmış veri (bkz.
    docs/roadmap.md "SeekBind 2.0" notu: ileride bunu programatik
    tüketecek bir orkestrasyon katmanı için).
    """

    success: bool
    booking_id: int | None = None
    alternatives: list[BookingAlternative] = Field(default_factory=list)

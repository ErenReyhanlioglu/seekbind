"""Kategori bazlı fiyat eşiği hesaplama — gerçek DB verisine dayanır.

"ucuz"/"pahalı" gibi göreceli kelimeler için LLM'in Türkiye fiyat
seviyelerini "tahmin etmesine" güvenilmiyor (bkz. ADR-0011 — smoke test'te
"ucuz dişçi" sorgusunun en pahalı diş kliniklerini döndürdüğü gözlendi).
Bunun yerine LLM sadece bir tercih sinyali (`cheap`/`expensive`) çıkarır,
gerçek sayısal eşik burada, o kategorinin gerçek fiyat dağılımından
hesaplanır.
"""

from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business

PricePreference = Literal["cheap", "expensive"]

# "ucuz" -> o kategorideki price_min'lerin (başlangıç fiyatı) en alt
# çeyrekliği (25. percentile), SearchFilters.max_price olarak kullanılır —
# filters.py'deki overlap mantığı max_price'ı price_min <= max_price ile
# karşılaştırıyor, bu yüzden percentile de price_min'den hesaplanmalı
# (price_max'tan hesaplarsak eşik gereğinden yüksek çıkar, filtre hiçbir
# şeyi elemez — bu tam olarak ilk implementasyonda yapılan hata, gerçek
# DB verisiyle doğrulandı: Diş Kliniği'nde price_min'in 25. percentile'ı
# 2174 TL iken price_max'ınki 5735 TL).
# "pahalı" -> price_max'ların (üst fiyat) en üst çeyrekliği (75. percentile),
# SearchFilters.min_price olarak kullanılır (filtre: price_max >= min_price).
CHEAP_PERCENTILE: float = 0.25
EXPENSIVE_PERCENTILE: float = 0.75


async def resolve_price_threshold(
    session: AsyncSession,
    category: str | None,
    preference: PricePreference | None,
) -> tuple[int | None, int | None]:
    """Kategori + tercih sinyalinden gerçek bir (min_price, max_price) eşiği hesaplar.

    `category` ya da `preference` yoksa `(None, None)` döner — hesaplayacak
    bir referans kategori yoksa (ya da kullanıcı fiyat konusunda bir tercih
    belirtmediyse) filtre uygulanmaz, tüm sonuçlar semantik uygunluğa göre
    sıralanır.
    """
    if category is None or preference is None:
        return None, None

    if preference == "cheap":
        result = await session.execute(
            select(
                func.percentile_cont(CHEAP_PERCENTILE).within_group(Business.price_min)
            ).where(Business.type_normalized == category)
        )
        max_price = result.scalar()
        return None, int(max_price) if max_price is not None else None

    result = await session.execute(
        select(
            func.percentile_cont(EXPENSIVE_PERCENTILE).within_group(Business.price_max)
        ).where(Business.type_normalized == category)
    )
    min_price = result.scalar()
    return int(min_price) if min_price is not None else None, None

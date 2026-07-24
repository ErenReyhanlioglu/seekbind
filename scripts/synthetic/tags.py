"""Gerçek veriden hesaplanan kural tabanlı etiketler (LLM kullanılmaz)."""

from scripts.constants import PRICE_RANGES_TL
from scripts.schemas import PriceRange, WorkingHours

# "uygun fiyatlı" / "premium" tag'i için kategori içindeki konum eşikleri
PRICE_TIER_LOW_RATIO: float = 0.33
PRICE_TIER_HIGH_RATIO: float = 0.67
# "yüksek puanlı" tag'i, ham rating yerine Bayesian düzeltilmiş
# weighted_rating (WR) üzerinden belirlenir (az yorumlu ama yüksek puanlı
# işletmelerin yanıltıcı şekilde öne çıkmaması için)
WEIGHTED_RATING_THRESHOLD: float = 4.8


def build_tags(
    type_normalized: str,
    online_available: bool,
    working_hours: WorkingHours,
    weighted_rating: float | None,
    price_range: PriceRange,
) -> list[str]:
    """Gerçek veriden hesaplanan kural tabanlı etiketler üretir."""
    tags: list[str] = []
    if online_available:
        tags.append("online")
    if working_hours.saturday.open is not None or working_hours.sunday.open is not None:
        tags.append("hafta sonu açık")
    if weighted_rating is not None and weighted_rating >= WEIGHTED_RATING_THRESHOLD:
        tags.append("yüksek puanlı")

    category = PRICE_RANGES_TL[type_normalized]
    cat_min, cat_max = category["min"], category["max"]
    business_mid = (price_range.min + price_range.max) / 2
    position = (business_mid - cat_min) / (cat_max - cat_min)
    if position <= PRICE_TIER_LOW_RATIO:
        tags.append("uygun fiyatlı")
    elif position >= PRICE_TIER_HIGH_RATIO:
        tags.append("premium")

    return tags

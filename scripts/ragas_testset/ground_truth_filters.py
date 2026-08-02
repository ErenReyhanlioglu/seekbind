"""Etiket bazlı işletme filtreleri — eski `scripts/build_ragas_ground_truth.py`'den
taşındı, artık `ragas_testset` paketinin bir parçası (bkz. ADR-0027).

`_apply_service_keyword_filter` YENİ — problem #1'in çözümü: `simple`
etiketli sorularda sorudaki spesifik ihtiyacı artık göz ardı etmiyor,
`turkish_lemma.py`'nin lemma-kümesi kesişimi kuralıyla eşleştiriyor.
"""

from datetime import time as time_type

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from backend.services.rag.pricing import resolve_price_threshold
from backend.services.search.availability import TIME_OF_DAY_RANGES, TimeOfDay
from scripts.load_embeddings import is_open_weekend
from scripts.ragas_testset.turkish_lemma import business_lemma_set, lemmas_of

_WEEKDAY_BUCKET_DAYS: frozenset[str] = frozenset(
    {"pazartesi", "salı", "çarşamba", "perşembe", "cuma"}
)
DAY_NAME_TO_BUCKET: dict[str, str] = {
    **{day: "weekday" for day in _WEEKDAY_BUCKET_DAYS},
    "cumartesi": "saturday",
    "pazar": "sunday",
}


def _parse_hhmm(value: str) -> time_type:
    hour, minute = value.split(":")
    return time_type(int(hour), int(minute))


def tag_value(tags: set[str], prefix: str) -> str | None:
    """`"day_of_week:cuma"` gibi `prefix:value` etiketlerinden değeri çıkarır."""
    for tag in tags:
        if tag.startswith(prefix):
            return tag.split(":", 1)[1]
    return None


def schedule_matches(
    working_hours: dict, day_bucket: str | None, time_of_day: TimeOfDay | None
) -> bool:
    """Canlı appointment_slots yerine haftalık working_hours programına bakar.

    `day_bucket=None` ise (soru sadece time_of_day içerip day_of_week
    içermiyorsa) her zaman True döner — gerçek pipeline'da da
    `build_availability_filter` aynı sebeple None döner (bkz.
    backend/services/rag/intent.py), tek başına time_of_day hiçbir filtre
    uygulamaz.
    """
    if day_bucket is None:
        return True
    hours = working_hours.get(day_bucket) or {}
    open_str, close_str = hours.get("open"), hours.get("close")
    if open_str is None or close_str is None:
        return False
    if time_of_day is None:
        return True
    open_time, close_time = _parse_hhmm(open_str), _parse_hhmm(close_str)
    range_start, range_end = TIME_OF_DAY_RANGES[time_of_day]
    return open_time < range_end and close_time > range_start


def apply_static_filters(businesses: list[Business], tags: set[str]) -> list[Business]:
    """Gender/online/hafta sonu gibi doğrudan sütun/JSONB kontrolleri.

    Gender eşleşmesi gerçek pipeline'daki gibi (filters.py) TAM eşleşme —
    "female" istenirse "unisex" işletmeler DAHIL EDİLMEZ, çünkü Qdrant'taki
    gerçek filtre de böyle çalışıyor.
    """
    if "gender:female" in tags:
        businesses = [b for b in businesses if b.gender == "female"]
    elif "gender:male" in tags:
        businesses = [b for b in businesses if b.gender == "male"]
    if "online_only" in tags:
        businesses = [b for b in businesses if b.online_available]
    if "weekend_open_only" in tags:
        businesses = [b for b in businesses if is_open_weekend(b.working_hours)]
    return businesses


def apply_service_keyword_filter(
    businesses: list[Business], tags: set[str]
) -> list[Business]:
    """`service_keyword:<terim>` etiketi varsa, terimle aynı lemma kümesini
    paylaşan işletmeleri döner (bkz. `turkish_lemma.py`, ADR-0027 problem #1)."""
    keyword = tag_value(tags, "service_keyword:")
    if keyword is None:
        return businesses
    keyword_lemmas = lemmas_of(keyword)
    return [
        b
        for b in businesses
        if keyword_lemmas & business_lemma_set(b.services, b.keywords)
    ]


async def apply_price_filter(
    session: AsyncSession, category: str, businesses: list[Business], tags: set[str]
) -> list[Business]:
    if "price_preference:cheap" in tags:
        preference = "cheap"
    elif "price_preference:expensive" in tags:
        preference = "expensive"
    else:
        return businesses
    min_price, max_price = await resolve_price_threshold(session, category, preference)
    return [
        b
        for b in businesses
        if (max_price is None or b.price_min <= max_price)
        and (min_price is None or b.price_max >= min_price)
    ]

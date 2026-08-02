"""Soru bazlı `expected_business_ids` çözümleyicileri — eski
`scripts/build_ragas_ground_truth.py`'den taşındı (bkz. ADR-0027).

`_resolve_filtered`'daki `has_hard_filter` kontrolüne `service_keyword:*`
eklendi — bu YENİ filtre de diğer sert filtreler (gün/fiyat/cinsiyet)
gibi davranıyor: eşleşen TÜM işletmeleri döner, TOP_K'ya kırpmaz (zaten
var olan davranışla tutarlı).
"""

from math import asin, cos, radians, sin, sqrt
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business, UserProfile
from backend.services.search.availability import TimeOfDay
from scripts.ragas_testset.business_lookup import fetch_category_businesses
from scripts.ragas_testset.ground_truth_filters import (
    DAY_NAME_TO_BUCKET,
    apply_price_filter,
    apply_service_keyword_filter,
    apply_static_filters,
    schedule_matches,
    tag_value,
)

REFERENCE_USER_ID: int = 1  # scripts/seed_test_user.py'deki tek referans kullanıcı
TOP_K: int = 5
NEAR_ME_CANDIDATE_POOL: int = (
    10  # near_me + rating_preference kombinasyonunda önce mesafeye göre daralt
)
EARTH_RADIUS_KM: float = 6371.0

# Kategori-bağımsız çapraz senaryolar — genel filtre yolunun kapsamadığı özel
# durumlar (bkz. evaluation/test_set.json'daki q077-q092, q099-q100).
MULTI_CATEGORY_MAP: dict[str, list[str]] = {
    "q077": ["Güzellik Salonu"],  # saç + cilt bakımı birlikte veren tek kategori
    "q078": ["Oto Servis"],  # tam kapsamlı oto servis klima kontrolünü de içerir
    "q079": ["Özel Ders", "Müzik Kursu"],  # gerçekten iki farklı hizmet
    "q080": ["Diş Kliniği", "Göz Doktoru"],  # gerçekten iki farklı uzmanlık
}
NAMED_BUSINESS_MAP: dict[str, str] = {
    "q089": "Ola Kuaför İzmit",
    "q090": "Yuvam Veteriner Kliniği",
    "q091": "Kocaeli 3. Noterliği",
    "q092": "TOSCAR Premium Service",
}
# q099: "eczane" 27 geçerli kategoriden biri değil (bkz. scripts/constants/
# business_types.py) — sorgulanacak bir tablo yok, tanım gereği boş.
# q100: "7/24 açık" veri modelinde temsil edilemiyor (working_hours sadece
# weekday/saturday/sunday saat aralığı tutuyor, gece yarısı açık kavramı yok)
# — bilinçli olarak boş, sistemin uydurmaması test ediliyor.
HARDCODED_EMPTY: frozenset[str] = frozenset({"q099", "q100"})

_HARD_FILTER_TAGS: frozenset[str] = frozenset(
    {
        "gender:female",
        "gender:male",
        "online_only",
        "weekend_open_only",
        "price_preference:cheap",
        "price_preference:expensive",
    }
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """backend.services.search.filters.compute_distance_km ile aynı hesap."""
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = (
        radians(v) for v in (lat1, lon1, lat2, lon2)
    )
    delta_lat, delta_lon = lat2_rad - lat1_rad, lon2_rad - lon1_rad
    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))


def _top_by_rating(
    businesses: list[Business], *, prefer_high: bool, limit: int
) -> list[int]:
    rated = [b for b in businesses if b.weighted_rating is not None]
    # cast: bu noktada rated'daki her b'nin weighted_rating'i yukarıdaki
    # filtreyle zaten None değil — Pyright bunu liste comprehension'ı
    # üzerinden takip edemiyor.
    rated.sort(key=lambda b: cast(float, b.weighted_rating), reverse=prefer_high)
    return [b.id for b in rated[:limit]]


def _has_hard_filter(tags: set[str], day_bucket: str | None) -> bool:
    return (
        day_bucket is not None
        or bool(tags & _HARD_FILTER_TAGS)
        or any(tag.startswith("service_keyword:") for tag in tags)
    )


async def _resolve_filtered(
    session: AsyncSession, category: str, tags: set[str]
) -> list[int]:
    """Genel yol: gender/online/hafta sonu/gün-saat/fiyat/servis-terimi filtrelerinin kesişimi.

    Hiçbir sert filtre yoksa ("simple"/"vague_implicit_category"), o
    kategorideki en yüksek weighted_rating'e sahip TOP_K işletme referans
    alınır — filtresiz bir "iyi X öner" sorusunda objektif "doğru cevap"
    zaten kalite sinyali (bkz. ADR-0004).
    """
    businesses = await fetch_category_businesses(session, category)
    businesses = apply_static_filters(businesses, tags)
    businesses = apply_service_keyword_filter(businesses, tags)

    day_name = tag_value(tags, "day_of_week:")
    day_bucket = DAY_NAME_TO_BUCKET[day_name] if day_name is not None else None
    time_of_day = cast(TimeOfDay | None, tag_value(tags, "time_of_day:"))
    businesses = [
        b
        for b in businesses
        if schedule_matches(b.working_hours, day_bucket, time_of_day)
    ]
    businesses = await apply_price_filter(session, category, businesses, tags)

    if not _has_hard_filter(tags, day_bucket):
        ranked = _top_by_rating(businesses, prefer_high=True, limit=TOP_K)
        if ranked:
            return ranked
        # Kategoride hiç weighted_rating yoksa (örn. Noter) kalite sinyaline
        # göre sıralayacak bir şey yok; sıfır sonuç dönmek yerine
        # kategorinin tamamından ilk TOP_K döner.
        return [b.id for b in businesses[:TOP_K]]
    return [b.id for b in businesses]


async def _resolve_near_me(
    session: AsyncSession, category: str, tags: set[str]
) -> list[int]:
    user = (
        await session.execute(
            select(UserProfile).where(UserProfile.id == REFERENCE_USER_ID)
        )
    ).scalar_one()
    if user.latitude is None or user.longitude is None:
        raise ValueError(
            f"Referans kullanıcı (id={REFERENCE_USER_ID}) için konum tanımlı değil, "
            "near_me sorularının ground truth'u hesaplanamaz"
        )
    user_lat, user_lon = user.latitude, user.longitude

    businesses = await fetch_category_businesses(session, category)
    businesses = apply_static_filters(businesses, tags)
    with_coords = [
        b for b in businesses if b.latitude is not None and b.longitude is not None
    ]
    # cast: with_coords'taki her b'nin latitude/longitude'u yukarıdaki
    # filtreyle zaten None değil — Pyright bunu takip edemiyor.
    with_coords.sort(
        key=lambda b: _haversine_km(
            user_lat, user_lon, cast(float, b.latitude), cast(float, b.longitude)
        )
    )
    nearest = with_coords[:NEAR_ME_CANDIDATE_POOL]
    if "rating_preference:high" in tags:
        return _top_by_rating(nearest, prefer_high=True, limit=TOP_K)
    return [b.id for b in nearest[:TOP_K]]


async def _resolve_named_business(
    session: AsyncSession, name_fragment: str
) -> list[int]:
    result = await session.execute(
        select(Business.id).where(Business.title.ilike(f"%{name_fragment}%"))
    )
    return list(result.scalars().all())


async def _resolve_multi_category(
    session: AsyncSession, categories: list[str]
) -> list[int]:
    ids: list[int] = []
    for category in categories:
        businesses = await fetch_category_businesses(session, category)
        ids.extend(_top_by_rating(businesses, prefer_high=True, limit=TOP_K))
    return ids


async def compute_expected_ids(session: AsyncSession, question: dict) -> list[int]:
    """Bir sorunun `intent_tags`/`category`'sinden beklenen işletme ID'lerini üretir."""
    question_id = question["id"]
    tags = set(question["intent_tags"])
    category = question["category"]

    if question_id in HARDCODED_EMPTY:
        return []
    if question_id in NAMED_BUSINESS_MAP:
        return await _resolve_named_business(session, NAMED_BUSINESS_MAP[question_id])
    if question_id in MULTI_CATEGORY_MAP:
        return await _resolve_multi_category(session, MULTI_CATEGORY_MAP[question_id])
    if "near_me" in tags:
        return await _resolve_near_me(session, category, tags)
    if "rating_preference:high" in tags:
        businesses = await fetch_category_businesses(session, category)
        return _top_by_rating(businesses, prefer_high=True, limit=TOP_K)
    if "rating_preference:low" in tags:
        businesses = await fetch_category_businesses(session, category)
        return _top_by_rating(businesses, prefer_high=False, limit=TOP_K)
    if "out_of_scope_category" in tags:
        return []
    return await _resolve_filtered(session, category, tags)

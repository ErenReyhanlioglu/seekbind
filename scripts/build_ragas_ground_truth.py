"""RAGAS test seti (`evaluation/test_set.json`) için `expected_business_ids`
hesaplayan tek seferlik script.

Her soru için "doğru" işletme kümesi, RAG pipeline'ındaki LLM'e (intent
parsing) hiç dokunmadan, doğrudan gerçek DB verisinden hesaplanır — amaç,
ground truth'un test edilen sistemden bağımsız/objektif kalması (bkz.
ADR-0009'daki evaluator bağımsızlığı gerekçesiyle aynı ilke).

Fiyat eşiği için `resolve_price_threshold` (backend.services.rag.pricing)
ve hafta sonu tespiti için `is_open_weekend` (scripts.load_embeddings) aynen
yeniden kullanılır — bunlar LLM çağırmayan, saf DB/veri fonksiyonları, ikinci
bir kopyasını yazmak tek gerçek kaynağı bozardı.

ÖNEMLİ KISIT: gün/saat bazlı sorular (`day_of_week`/`time_of_day`) canlı
`appointment_slots` tablosuna DEĞİL, işletmenin haftalık `working_hours`
programına bakar. `appointment_slots`, seed anından itibaren sadece
`SLOT_GENERATION_DAYS_AHEAD` kadar üretiliyor (bkz.
scripts/synthetic/schedule.py) — bu test seti ADR-0009 gereği sabit kalıp
haftalar/aylar sonra tekrar tekrar çalıştırılacağı için, o an "bugün"e göre
üretilmiş somut slot satırlarına bağlı bir ground truth her çalıştırmada
sessizce bozulurdu. Haftalık program (working_hours) zamana bağlı değil,
bu yüzden tercih edildi. Ayrıca veri modelinde pazartesi-cuma tek bir
"weekday" kovasında toplu tutuluyor (bkz. scripts/synthetic/schedule.py
`_day_hours`) — yani "pazartesi" ile "cuma" sorgusu şema açısından aynı
saatlere bakar, sadece cumartesi/pazar ayrı.

Çıktı: `evaluation/test_set.json`'a `expected_business_ids` eklenir (yerinde
günceller). Ayrıca referans metni yazarken kullanılmak üzere çözümlenen
işletmelerin gerçek alanları (başlık, fiyat, puan vb.) scratchpad'e ayrı bir
JSON olarak yazılır — bu ikinci dosya nihai `test_set.json`'ın bir parçası
değil, sadece bu oturumun ara çalışma dosyası.

Kullanım:
    uv run python -m scripts.build_ragas_ground_truth
"""

import asyncio
import json
from datetime import time as time_type
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business, UserProfile
from backend.db.session import get_session_factory
from backend.services.rag.pricing import resolve_price_threshold
from backend.services.search.availability import TIME_OF_DAY_RANGES, TimeOfDay
from scripts.load_embeddings import is_open_weekend

TEST_SET_PATH: Path = Path("evaluation/test_set.json")
DETAILS_OUTPUT_PATH: Path = Path(
    r"C:\Users\Eren\AppData\Local\Temp\claude\c--Users-Eren-Desktop-visual-studio-seekbind"
    r"\431cba88-266e-4abd-8994-986fe06a58f4\scratchpad\ground_truth_details.json"
)

REFERENCE_USER_ID: int = 1  # scripts/seed_test_user.py'deki tek referans kullanıcı
TOP_K: int = 5
NEAR_ME_CANDIDATE_POOL: int = (
    10  # near_me + rating_preference kombinasyonunda önce mesafeye göre daralt
)
EARTH_RADIUS_KM: float = 6371.0

_WEEKDAY_BUCKET_DAYS: frozenset[str] = frozenset(
    {"pazartesi", "salı", "çarşamba", "perşembe", "cuma"}
)
DAY_NAME_TO_BUCKET: dict[str, str] = {
    **{day: "weekday" for day in _WEEKDAY_BUCKET_DAYS},
    "cumartesi": "saturday",
    "pazar": "sunday",
}

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


def _parse_hhmm(value: str) -> time_type:
    hour, minute = value.split(":")
    return time_type(int(hour), int(minute))


def _tag_value(tags: set[str], prefix: str) -> str | None:
    """`"day_of_week:cuma"` gibi `prefix:value` etiketlerinden değeri çıkarır."""
    for tag in tags:
        if tag.startswith(prefix):
            return tag.split(":", 1)[1]
    return None


def _schedule_matches(
    working_hours: dict, day_bucket: str | None, time_of_day: TimeOfDay | None
) -> bool:
    """Canlı appointment_slots yerine haftalık working_hours programına bakar (bkz. modül docstring'i).

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


async def _fetch_category_businesses(
    session: AsyncSession, category: str
) -> list[Business]:
    result = await session.execute(
        select(Business).where(Business.type_normalized == category)
    )
    return list(result.scalars().all())


def _apply_static_filters(businesses: list[Business], tags: set[str]) -> list[Business]:
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


async def _apply_price_filter(
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


def _top_by_rating(
    businesses: list[Business], *, prefer_high: bool, limit: int
) -> list[int]:
    rated = [b for b in businesses if b.weighted_rating is not None]
    # cast: bu noktada rated'daki her b'nin weighted_rating'i yukarıdaki
    # filtreyle zaten None değil — Pyright bunu liste comprehension'ı
    # üzerinden takip edemiyor (bkz. aynı gerekçe search/service.py'de).
    rated.sort(key=lambda b: cast(float, b.weighted_rating), reverse=prefer_high)
    return [b.id for b in rated[:limit]]


async def _resolve_filtered(
    session: AsyncSession, category: str, tags: set[str]
) -> list[int]:
    """Genel yol: gender/online/hafta sonu/gün-saat/fiyat filtrelerinin kesişimi.

    Hiçbir sert filtre yoksa ("simple"/"vague_implicit_category"), o
    kategorideki en yüksek weighted_rating'e sahip TOP_K işletme referans
    alınır — filtresiz bir "iyi X öner" sorusunda objektif "doğru cevap"
    zaten kalite sinyali (bkz. ADR-0004).
    """
    businesses = await _fetch_category_businesses(session, category)
    businesses = _apply_static_filters(businesses, tags)

    day_name = _tag_value(tags, "day_of_week:")
    day_bucket = DAY_NAME_TO_BUCKET[day_name] if day_name is not None else None
    # cast: test_set.json'daki time_of_day değerleri her zaman TimeOfDay'in
    # 3 literal değerinden biri (bkz. intent.py'deki aynı Literal) — ama
    # _tag_value düz bir str döndürüyor, Pyright bunu daraltamıyor.
    time_of_day = cast(TimeOfDay | None, _tag_value(tags, "time_of_day:"))
    businesses = [
        b
        for b in businesses
        if _schedule_matches(b.working_hours, day_bucket, time_of_day)
    ]
    businesses = await _apply_price_filter(session, category, businesses, tags)

    has_hard_filter = day_bucket is not None or bool(
        tags
        & {
            "gender:female",
            "gender:male",
            "online_only",
            "weekend_open_only",
            "price_preference:cheap",
            "price_preference:expensive",
        }
    )
    if not has_hard_filter:
        ranked = _top_by_rating(businesses, prefer_high=True, limit=TOP_K)
        if ranked:
            return ranked
        # Kategoride hiç weighted_rating yoksa (örn. Noter — bkz. gerçek DB
        # kontrolü) kalite sinyaline göre sıralayacak bir şey yok; sıfır
        # sonuç dönmek yerine kategorinin tamamından ilk TOP_K döner.
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

    businesses = await _fetch_category_businesses(session, category)
    businesses = _apply_static_filters(businesses, tags)
    with_coords = [
        b for b in businesses if b.latitude is not None and b.longitude is not None
    ]
    # cast: with_coords'taki her b'nin latitude/longitude'u yukarıdaki
    # filtreyle zaten None değil — Pyright bunu liste comprehension'ı
    # üzerinden takip edemiyor (bkz. _top_by_rating'deki aynı gerekçe).
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
        businesses = await _fetch_category_businesses(session, category)
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
        businesses = await _fetch_category_businesses(session, category)
        return _top_by_rating(businesses, prefer_high=True, limit=TOP_K)
    if "rating_preference:low" in tags:
        businesses = await _fetch_category_businesses(session, category)
        return _top_by_rating(businesses, prefer_high=False, limit=TOP_K)
    if "out_of_scope_category" in tags:
        return []
    return await _resolve_filtered(session, category, tags)


async def _fetch_details(session: AsyncSession, business_ids: list[int]) -> list[dict]:
    """Referans metni yazarken kullanılacak gerçek işletme alanlarını döner."""
    if not business_ids:
        return []
    result = await session.execute(
        select(Business).where(Business.id.in_(business_ids))
    )
    return [
        {
            "id": b.id,
            "title": b.title,
            "type_normalized": b.type_normalized,
            "price_min": b.price_min,
            "price_max": b.price_max,
            "weighted_rating": b.weighted_rating,
            "gender": b.gender,
            "online_available": b.online_available,
            "services": b.services,
            "address": b.address,
            "rich_description": b.rich_description,
        }
        for b in result.scalars().all()
    ]


async def main() -> None:
    questions = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    details: dict[str, list[dict]] = {}

    session_factory = get_session_factory()
    async with session_factory() as session:
        for question in questions:
            expected_ids = await compute_expected_ids(session, question)
            question["expected_business_ids"] = expected_ids
            details[question["id"]] = await _fetch_details(session, expected_ids)

    TEST_SET_PATH.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    DETAILS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DETAILS_OUTPUT_PATH.write_text(
        json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    empty_count = sum(1 for q in questions if not q["expected_business_ids"])
    print(f"{len(questions)} soru işlendi, {empty_count} tanesi boş küme döndürdü.")


if __name__ == "__main__":
    asyncio.run(main())

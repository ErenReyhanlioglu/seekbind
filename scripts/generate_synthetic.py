"""Ham SerpAPI verisini temizler ve kural tabanlı alanlarla zenginleştirir.

data/raw/businesses.jsonl'ı okur, reviews_original'dan doğru yorum sayısını
parse eder, scripts/constants paketindeki sabitlerden hizmet/fiyat/süre/
online/cinsiyet/çalışma saati alanlarını atar, müsait ve dolu randevu
slotlarını üretir. rich_description burada üretilmez (None kalır),
onu enrich_with_llm.py doldurur.
"""

import json
import logging
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.constants import (
    APPOINTMENT_DURATIONS_MIN,
    DEFAULT_GENDER_PREFERENCE_WEIGHTS,
    GENDER_PREFERENCE_WEIGHTS,
    ONLINE_AVAILABLE,
    PRICE_RANGES_TL,
    QUERY_TERM_TO_TYPE,
    SATURDAY_OPEN_PROBABILITY,
    SERVICE_TAXONOMY,
    SUNDAY_OPEN_PROBABILITY,
    WORKING_HOURS_JITTER_OPTIONS_MIN,
    WORKING_HOURS_TEMPLATE,
)
from scripts.schemas import PriceRange, ProcessedBusinessRecord, WorkingHours, WorkingHoursDay

logger = logging.getLogger(__name__)

INPUT_FILE_PATH: Path = Path("data/raw/businesses.jsonl")
OUTPUT_FILE_PATH: Path = Path("data/processed/businesses.jsonl")

MIN_SERVICES_PER_BUSINESS: int = 3
MAX_SERVICES_PER_BUSINESS: int = 6
SLOT_GENERATION_DAYS_AHEAD: int = 7
BOOKED_SLOT_PROBABILITY: float = 0.3

TIME_FORMAT: str = "%H:%M"
SLOT_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M"
# "(384)" ya da "(1,3 B)" gibi metinlerden sayıyı ve varsa "B" (bin) ekini yakalar
REVIEW_COUNT_PATTERN = re.compile(r"\(([\d.,]+)\s*(B)?\)", re.IGNORECASE)


def load_raw_records(path: Path) -> list[dict[str, Any]]:
    """data/raw/businesses.jsonl'daki tüm kayıtları okur."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records


def parse_review_count(reviews_original: str | None, fallback: int) -> int:
    """reviews_original metninden doğru yorum sayısını çıkarır.

    SerpAPI'nin sayısal `reviews` alanı Türkçe "B" (bin) ekini yanlış
    parse edebiliyor (örn. "(1,3 B)" -> 1300000000). Bu yüzden kaynak
    olarak her zaman reviews_original metni kullanılır.
    """
    if not reviews_original:
        return fallback
    match = REVIEW_COUNT_PATTERN.search(reviews_original)
    if not match:
        return fallback
    number_str, bin_suffix = match.groups()
    number_str = number_str.replace(".", "").replace(",", ".")
    try:
        value = float(number_str)
    except ValueError:
        return fallback
    if bin_suffix:
        value *= 1000
    return int(round(value))


def weighted_sample_without_replacement(pool: dict[str, int], k: int) -> list[str]:
    """Ağırlıklı, tekrarsız örnekleme (aynı öğe iki kez seçilmez)."""
    remaining = list(pool.items())
    selected: list[str] = []
    for _ in range(min(k, len(remaining))):
        names = [item[0] for item in remaining]
        weights = [item[1] for item in remaining]
        chosen = random.choices(names, weights=weights, k=1)[0]
        selected.append(chosen)
        remaining = [item for item in remaining if item[0] != chosen]
    return selected


def weighted_choice(pool: dict[str, float]) -> str:
    """Ağırlıklı, tekil seçim (gender gibi kategorik alanlar için)."""
    return random.choices(list(pool.keys()), weights=list(pool.values()), k=1)[0]


def pick_services(type_normalized: str) -> list[str]:
    """İşletme tipine göre ağırlıklı, tekrarsız hizmet seçimi yapar."""
    count = random.randint(MIN_SERVICES_PER_BUSINESS, MAX_SERVICES_PER_BUSINESS)
    return weighted_sample_without_replacement(SERVICE_TAXONOMY[type_normalized], count)


def pick_gender(type_normalized: str) -> str:
    """İşletme tipine göre ağırlıklı cinsiyet tercihi seçer."""
    weights = GENDER_PREFERENCE_WEIGHTS.get(type_normalized, DEFAULT_GENDER_PREFERENCE_WEIGHTS)
    return weighted_choice(weights)


def _apply_jitter(
    template_hours: tuple[str, str] | None,
    open_probability: float | None,
    open_jitter_min: int,
    close_jitter_min: int,
) -> WorkingHoursDay:
    """Bir günün taban saatine jitter uygular, olasılığa göre kapalı sayabilir."""
    if template_hours is None:
        return WorkingHoursDay(open=None, close=None)
    if open_probability is not None and random.random() > open_probability:
        return WorkingHoursDay(open=None, close=None)

    open_str, close_str = template_hours
    open_dt = datetime.strptime(open_str, TIME_FORMAT) + timedelta(minutes=open_jitter_min)
    close_dt = datetime.strptime(close_str, TIME_FORMAT) + timedelta(minutes=close_jitter_min)
    return WorkingHoursDay(open=open_dt.strftime(TIME_FORMAT), close=close_dt.strftime(TIME_FORMAT))


def _pick_jitter_minutes() -> int:
    """WORKING_HOURS_JITTER_OPTIONS_MIN'den işaretli (+/-) bir sapma seçer."""
    return random.choice(WORKING_HOURS_JITTER_OPTIONS_MIN) * random.choice((-1, 1))


def build_working_hours(type_normalized: str) -> WorkingHours:
    """İşletme için jitter uygulanmış, olasılığa göre hafta sonu ayarlı çalışma saatleri üretir."""
    template = WORKING_HOURS_TEMPLATE[type_normalized]
    open_jitter = _pick_jitter_minutes()
    close_jitter = _pick_jitter_minutes()

    weekday = _apply_jitter(template["weekday"], None, open_jitter, close_jitter)
    saturday = _apply_jitter(
        template["saturday"], SATURDAY_OPEN_PROBABILITY.get(type_normalized), open_jitter, close_jitter
    )
    sunday = _apply_jitter(
        template["sunday"], SUNDAY_OPEN_PROBABILITY.get(type_normalized), open_jitter, close_jitter
    )
    return WorkingHours(weekday=weekday, saturday=saturday, sunday=sunday)


def _day_hours(working_hours: WorkingHours, day: date) -> WorkingHoursDay:
    """Haftanın gününe (0=Pazartesi...6=Pazar) göre ilgili çalışma saatini döner."""
    weekday_index = day.weekday()
    if weekday_index == 5:
        return working_hours.saturday
    if weekday_index == 6:
        return working_hours.sunday
    return working_hours.weekday


def generate_slots(working_hours: WorkingHours, duration_min: int) -> tuple[list[str], list[str]]:
    """Önümüzdeki SLOT_GENERATION_DAYS_AHEAD gün için müsait/dolu slotları üretir."""
    available: list[str] = []
    booked: list[str] = []
    start_date = datetime.now().date() + timedelta(days=1)

    for offset in range(SLOT_GENERATION_DAYS_AHEAD):
        current_day = start_date + timedelta(days=offset)
        hours = _day_hours(working_hours, current_day)
        if hours.open is None or hours.close is None:
            continue

        slot_start = datetime.combine(current_day, datetime.strptime(hours.open, TIME_FORMAT).time())
        day_close = datetime.combine(current_day, datetime.strptime(hours.close, TIME_FORMAT).time())

        while slot_start + timedelta(minutes=duration_min) <= day_close:
            slot_str = slot_start.strftime(SLOT_DATETIME_FORMAT)
            target = booked if random.random() < BOOKED_SLOT_PROBABILITY else available
            target.append(slot_str)
            slot_start += timedelta(minutes=duration_min)

    return available, booked


def build_processed_record(raw: dict[str, Any]) -> ProcessedBusinessRecord:
    """Tek bir ham kayıttan tam bir ProcessedBusinessRecord üretir."""
    data = raw["data"]
    type_normalized = QUERY_TERM_TO_TYPE[raw["query_term"]]
    duration = random.choice(APPOINTMENT_DURATIONS_MIN[type_normalized])
    working_hours = build_working_hours(type_normalized)
    available_slots, booked_slots = generate_slots(working_hours, duration)
    price = PRICE_RANGES_TL[type_normalized]

    return ProcessedBusinessRecord(
        place_id=raw["place_id"],
        title=data.get("title", ""),
        type_normalized=type_normalized,
        rating=data.get("rating"),
        reviews=parse_review_count(data.get("reviews_original"), data.get("reviews", 0)),
        address=data.get("address"),
        phone=data.get("phone"),
        gps_coordinates=data.get("gps_coordinates"),
        services=pick_services(type_normalized),
        price_range_tl=PriceRange(min=price["min"], max=price["max"]),
        appointment_duration_min=duration,
        online_available=ONLINE_AVAILABLE[type_normalized],
        gender=pick_gender(type_normalized),
        working_hours=working_hours,
        available_slots=available_slots,
        booked_slots=booked_slots,
    )


def main() -> None:
    """Ham veriyi işleyip data/processed/businesses.jsonl'a yazar."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    raw_records = load_raw_records(INPUT_FILE_PATH)
    logger.info("%d ham kayıt okundu", len(raw_records))

    OUTPUT_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE_PATH.open("w", encoding="utf-8") as f:
        for raw in raw_records:
            record = build_processed_record(raw)
            f.write(record.model_dump_json() + "\n")

    logger.info("Tamamlandı. %d işlenmiş kayıt data/processed/businesses.jsonl'a yazıldı", len(raw_records))


if __name__ == "__main__":
    main()

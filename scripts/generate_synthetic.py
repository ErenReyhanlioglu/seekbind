"""Ham SerpAPI verisini temizler ve kural tabanlı alanlarla zenginleştirir.

data/raw/businesses.jsonl'ı okur, reviews_original'dan doğru yorum sayısını
parse eder, scripts/synthetic ve scripts/constants paketlerindeki kurallarla
hizmet/fiyat/süre/online/cinsiyet/çalışma saati/tag alanlarını atar, müsait
ve dolu randevu slotlarını üretir. rich_description ve keywords burada
üretilmez (boş kalır), onları enrich_with_llm.py doldurur.
"""

import json
import logging
import random
from pathlib import Path
from typing import Any

from scripts.constants import APPOINTMENT_DURATIONS_MIN, ONLINE_AVAILABLE, QUERY_TERM_TO_TYPE
from scripts.schemas import ProcessedBusinessRecord
from scripts.synthetic import (
    assign_genders,
    build_tags,
    build_working_hours,
    compute_rating_baseline,
    compute_weighted_rating,
    generate_slots,
    parse_review_count,
    pick_price_range,
    pick_services,
)

logger = logging.getLogger(__name__)

INPUT_FILE_PATH: Path = Path("data/raw/businesses.jsonl")
OUTPUT_FILE_PATH: Path = Path("data/processed/businesses.jsonl")


def load_raw_records(path: Path) -> list[dict[str, Any]]:
    """data/raw/businesses.jsonl'daki tüm kayıtları okur."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records


def build_processed_record(
    raw: dict[str, Any],
    mean_rating: float,
    confidence_m: int,
    gender_assignment: dict[str, str],
) -> ProcessedBusinessRecord:
    """Tek bir ham kayıttan tam bir ProcessedBusinessRecord üretir."""
    data = raw["data"]
    type_normalized = QUERY_TERM_TO_TYPE[raw["query_term"]]
    duration = random.choice(APPOINTMENT_DURATIONS_MIN[type_normalized])
    working_hours = build_working_hours(type_normalized)
    available_slots, booked_slots = generate_slots(working_hours, duration)
    price_range = pick_price_range(type_normalized)
    online_available = ONLINE_AVAILABLE[type_normalized]
    rating = data.get("rating")
    reviews = parse_review_count(data.get("reviews_original"), data.get("reviews", 0))
    weighted_rating = compute_weighted_rating(rating, reviews, mean_rating, confidence_m)
    tags = build_tags(type_normalized, online_available, working_hours, weighted_rating, price_range)

    return ProcessedBusinessRecord(
        place_id=raw["place_id"],
        title=data.get("title", ""),
        type_normalized=type_normalized,
        rating=rating,
        weighted_rating=weighted_rating,
        reviews=reviews,
        address=data.get("address"),
        phone=data.get("phone"),
        gps_coordinates=data.get("gps_coordinates"),
        services=pick_services(type_normalized),
        price_range_tl=price_range,
        appointment_duration_min=duration,
        online_available=online_available,
        gender=gender_assignment[raw["place_id"]],
        working_hours=working_hours,
        available_slots=available_slots,
        booked_slots=booked_slots,
        tags=tags,
    )


def main() -> None:
    """Ham veriyi işleyip data/processed/businesses.jsonl'a yazar."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    raw_records = load_raw_records(INPUT_FILE_PATH)
    logger.info("%d ham kayıt okundu", len(raw_records))

    mean_rating, confidence_m = compute_rating_baseline(raw_records)
    logger.info("Bayesian taban: ortalama puan=%.3f, güven eşiği (m)=%d", mean_rating, confidence_m)
    gender_assignment = assign_genders(raw_records)

    OUTPUT_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE_PATH.open("w", encoding="utf-8") as f:
        for raw in raw_records:
            record = build_processed_record(raw, mean_rating, confidence_m, gender_assignment)
            f.write(record.model_dump_json() + "\n")

    logger.info("Tamamlandı. %d işlenmiş kayıt data/processed/businesses.jsonl'a yazıldı", len(raw_records))


if __name__ == "__main__":
    main()

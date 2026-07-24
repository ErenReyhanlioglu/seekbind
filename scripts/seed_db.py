"""data/processed/businesses_enriched.jsonl'daki veriyi Postgres'e yükler.

business_types ve businesses tabloları toplu upsert (varsa güncelle,
yoksa ekle) ile doldurulur. appointment_slots tablosu truncate-and-load
(önce temizle, sonra toplu ekle) ile doldurulur — slotlar "bugünden
itibaren N gün" mantığıyla üretildiği için (generate_synthetic.py) her
çalıştırmada baştan geçerli hale gelir, upsert kavramı anlamlı değildir.

Not: Bu script, backend/db/session.py'deki async DB katmanını kullandığı
için (sync bir DB erişim yolu tanımlı değil) async yazılmıştır — diğer
scripts/ araçlarının aksine.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AppointmentSlot, Business, BusinessType
from backend.db.session import get_session_factory
from scripts.constants import get_type_to_category_group
from scripts.schemas import ProcessedBusinessRecord

logger = logging.getLogger(__name__)

INPUT_FILE_PATH: Path = Path("data/processed/businesses_enriched.jsonl")
SEARCH_VECTOR_LANGUAGE: str = "turkish"
SLOT_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M"


def load_enriched_records(path: Path) -> list[ProcessedBusinessRecord]:
    """data/processed/businesses_enriched.jsonl'daki kayıtları okur."""
    records: list[ProcessedBusinessRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            records.append(ProcessedBusinessRecord(**json.loads(line)))
    return records


async def seed_business_types(session: AsyncSession) -> None:
    """business_types tablosunu toplu upsert ile doldurur (27 sabit satır)."""
    rows = [{"name": name, "category_group": group} for name, group in get_type_to_category_group().items()]
    stmt = pg_insert(BusinessType).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[BusinessType.name],
        set_={"category_group": stmt.excluded.category_group},
    )
    await session.execute(stmt)


def _build_search_text(record: ProcessedBusinessRecord) -> str:
    """search_vector için title + services + description + keywords'ü birleştirir."""
    parts = [
        record.title,
        " ".join(record.services),
        record.rich_description or "",
        " ".join(record.keywords),
    ]
    return " ".join(parts)


def _business_row(record: ProcessedBusinessRecord) -> dict:
    """Tek bir kayıttan businesses tablosu için satır sözlüğü üretir."""
    gps = record.gps_coordinates or {}
    return {
        "place_id": record.place_id,
        "title": record.title,
        "type_normalized": record.type_normalized,
        "rating": record.rating,
        "weighted_rating": record.weighted_rating,
        "reviews": record.reviews,
        "address": record.address,
        "phone": record.phone,
        "latitude": gps.get("latitude"),
        "longitude": gps.get("longitude"),
        "price_min": record.price_range_tl.min,
        "price_max": record.price_range_tl.max,
        "appointment_duration_min": record.appointment_duration_min,
        "online_available": record.online_available,
        "gender": record.gender,
        "services": record.services,
        "tags": record.tags,
        "keywords": record.keywords,
        "working_hours": record.working_hours.model_dump(),
        "rich_description": record.rich_description,
        "search_vector": func.to_tsvector(SEARCH_VECTOR_LANGUAGE, _build_search_text(record)),
    }


async def seed_businesses(session: AsyncSession, records: list[ProcessedBusinessRecord]) -> dict[str, int]:
    """businesses tablosunu toplu upsert ile doldurur, place_id -> id eşlemesini döner."""
    rows = [_business_row(record) for record in records]
    stmt = pg_insert(Business).values(rows)

    skip_on_update = {"id", "place_id", "created_at", "updated_at"}
    update_columns = {
        col.name: stmt.excluded[col.name] for col in Business.__table__.columns if col.name not in skip_on_update
    }
    update_columns["updated_at"] = func.now()

    stmt = stmt.on_conflict_do_update(index_elements=[Business.place_id], set_=update_columns)
    stmt = stmt.returning(Business.id, Business.place_id)

    result = await session.execute(stmt)
    return {place_id: business_id for business_id, place_id in result.all()}


async def seed_appointment_slots(
    session: AsyncSession,
    records: list[ProcessedBusinessRecord],
    place_id_to_business_id: dict[str, int],
) -> int:
    """appointment_slots tablosunu truncate-and-load ile doldurur."""
    await session.execute(delete(AppointmentSlot))

    rows = []
    for record in records:
        business_id = place_id_to_business_id[record.place_id]
        for slot in record.available_slots:
            rows.append(
                {
                    "business_id": business_id,
                    "start_time": datetime.strptime(slot, SLOT_DATETIME_FORMAT),
                    "is_booked": False,
                }
            )
        for slot in record.booked_slots:
            rows.append(
                {
                    "business_id": business_id,
                    "start_time": datetime.strptime(slot, SLOT_DATETIME_FORMAT),
                    "is_booked": True,
                }
            )

    if rows:
        await session.execute(AppointmentSlot.__table__.insert(), rows)
    return len(rows)


async def main() -> None:
    """data/processed/businesses_enriched.jsonl'ı okuyup Postgres'e yükler."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    records = load_enriched_records(INPUT_FILE_PATH)
    logger.info("%d kayıt okundu, Postgres'e yükleniyor", len(records))

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await seed_business_types(session)
            place_id_to_business_id = await seed_businesses(session, records)
            slot_count = await seed_appointment_slots(session, records, place_id_to_business_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    logger.info("Tamamlandı. %d işletme, %d slot yüklendi", len(place_id_to_business_id), slot_count)


if __name__ == "__main__":
    asyncio.run(main())

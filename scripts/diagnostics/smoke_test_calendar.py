"""feature/calendar-service için gerçek DB'ye karşı manuel doğrulama script'i.

Otomatik test değil — `book_appointment()`'ın gerçek veriyle dört ana
davranışını gözle kontrol etmek içindir: başarılı rezervasyon, slot zaten
dolu, kullanıcının kendi randevusuyla (farklı işletme dahil) çakışma, ve
fiyat kısıtının çapraz-işletme alternatiflerini gerçekten daraltması.

Test senaryoları veritabanındaki GERÇEK veriden dinamik olarak seçilir
(sabit ID'ler hardcode edilmez) — böylece script farklı seed çalıştırmaları
arasında da anlamlı kalır.

DİKKAT: Tüm senaryolar tek bir transaction içinde çalışır ve sonunda
COMMIT edilmez, ROLLBACK edilir — böylece script tekrar tekrar
çalıştırılabilir, dev veritabanına kalıcı sahte booking bırakmaz.
`book_appointment()`'ın gerçekten kalıcı yazdığı, ADR-0017/roadmap'teki
ilk uçtan uca doğrulamada (elle, bu script dışında) zaten teyit edildi.

Kullanım:
    uv run python -m scripts.diagnostics.smoke_test_calendar
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import BookResponse
from backend.db.models import AppointmentSlot, Booking, Business, UserProfile
from backend.db.session import get_session_factory
from backend.services.calendar import book_appointment

logger = logging.getLogger(__name__)

RESULTS_DIR: Path = Path("evaluation/results/diagnostics/calendar_smoke_test")
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"


def _print_and_record(title: str, result: BookResponse) -> dict:
    """Sonucu terminale yazdırır, JSON'a kaydedilecek yapıyı döner.

    `alternatives`, `BookingAlternative`'ın TÜM alanlarıyla (adres,
    telefon, hizmetler, fiyat vb. dahil — `ProviderResult`'ın zenginliği)
    kaydedilir; `model_dump` kullanılır, elle alan alan kopyalanmaz —
    böylece şemaya yeni bir alan eklenirse bu script elle güncellenmesine
    gerek kalmadan onu da yakalar.
    """
    print(f"\n=== {title} ===")
    print(f"  success={result.success} booking_id={result.booking_id}")
    for i, alt in enumerate(result.alternatives, start=1):
        print(
            f"    {i}. {alt.business.title[:45]!r} ({alt.business.type_normalized}) — "
            f"{alt.business.price_min}-{alt.business.price_max}TL — puan={alt.business.weighted_rating} — "
            f"mesafe={alt.business.distance_km} — "
            f"adres={alt.business.address} — slot={alt.appointment_slot_id} start={alt.start_time}"
        )
    return {
        "title": title,
        "success": result.success,
        "booking_id": result.booking_id,
        "alternatives": [alt.model_dump(mode="json") for alt in result.alternatives],
    }


async def _find_conflict_free_slot(session: AsyncSession, user_id: int) -> int | None:
    """Kullanıcının hiç randevusu olmadığı bir günde, boş bir slot bulur (başarılı rezervasyon senaryosu için)."""
    booked_days = await session.execute(
        select(AppointmentSlot.start_time)
        .join(Booking, Booking.appointment_slot_id == AppointmentSlot.id)
        .where(Booking.user_id == user_id)
    )
    busy_dates = {row[0].date() for row in booked_days.all()}

    candidates = await session.execute(
        select(AppointmentSlot.id, AppointmentSlot.start_time).where(AppointmentSlot.is_booked.is_(False))
    )
    for slot_id, start_time in candidates.all():
        if start_time.date() not in busy_dates:
            return slot_id
    return None


async def _find_other_booked_slot(session: AsyncSession, user_id: int) -> int | None:
    """Kullanıcının KENDİ rezervasyonu olmayan, başkası tarafından dolu bir slot bulur."""
    own_slot_ids = (
        await session.execute(select(Booking.appointment_slot_id).where(Booking.user_id == user_id))
    ).scalars().all()
    result = await session.execute(
        select(AppointmentSlot.id)
        .where(AppointmentSlot.is_booked.is_(True), AppointmentSlot.id.not_in(own_slot_ids))
        .order_by(AppointmentSlot.id)
    )
    return result.scalars().first()


async def _find_cross_business_conflict_slot(session: AsyncSession, user_id: int) -> int | None:
    """Kullanıcının mevcut randevularından birinin zaman aralığına denk gelen,
    FARKLI bir işletmedeki boş bir slot bulur (çapraz işletme çakışma senaryosu için)."""
    schedule = await session.execute(
        select(AppointmentSlot.business_id, AppointmentSlot.start_time, Business.appointment_duration_min)
        .join(Booking, Booking.appointment_slot_id == AppointmentSlot.id)
        .join(Business, AppointmentSlot.business_id == Business.id)
        .where(Booking.user_id == user_id)
    )
    for business_id, start, duration in schedule.all():
        end = start + timedelta(minutes=duration)
        candidate = await session.execute(
            select(AppointmentSlot.id)
            .where(
                AppointmentSlot.business_id != business_id,
                AppointmentSlot.is_booked.is_(False),
                AppointmentSlot.start_time >= start,
                AppointmentSlot.start_time < end,
            )
            .limit(1)
        )
        slot_id = candidate.scalar_one_or_none()
        if slot_id is not None:
            return slot_id
    return None


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

    scenarios: list[dict] = []
    session_factory = get_session_factory()
    async with session_factory() as session:
        user = (await session.execute(select(UserProfile))).scalars().first()
        if user is None:
            logger.error("UserProfile bulunamadı — önce 'uv run python -m scripts.seed_test_user' çalıştırılmalı")
            return

        free_slot_id = await _find_conflict_free_slot(session, user.id)
        if free_slot_id is not None:
            result = await book_appointment(session, user.id, free_slot_id)
            scenarios.append(_print_and_record("Başarılı rezervasyon", result))

        other_booked_id = await _find_other_booked_slot(session, user.id)
        if other_booked_id is not None:
            result = await book_appointment(session, user.id, other_booked_id)
            scenarios.append(_print_and_record("Slot başkası tarafından zaten dolu", result))

            result_filtered = await book_appointment(session, user.id, other_booked_id, max_price=1000)
            scenarios.append(_print_and_record("Aynı senaryo, max_price=1000 filtresiyle", result_filtered))

            result_near = await book_appointment(session, user.id, other_booked_id, near_me=True)
            scenarios.append(_print_and_record("Aynı senaryo, near_me=True (mesafeye göre sıralı)", result_near))

        cross_conflict_id = await _find_cross_business_conflict_slot(session, user.id)
        if cross_conflict_id is not None:
            result = await book_appointment(session, user.id, cross_conflict_id)
            scenarios.append(_print_and_record("Kullanıcının başka işletmedeki randevusuyla çakışma", result))

        # Hiçbir senaryo gerçekten kalıcı yazılmasın diye bilerek commit değil rollback.
        await session.rollback()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    output_path = RESULTS_DIR / f"{timestamp}.json"
    output_path.write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Sonuçlar kaydedildi: %s", output_path)
    print(f"\nSonuçlar kaydedildi: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

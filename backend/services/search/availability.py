"""İki fazlı tarih/saat müsaitlik kontrolünün ikinci fazı.

Qdrant/BM25 sadece statik özelliklere göre aday havuzunu daraltır (bkz.
bm25.py, vector.py); randevu slotu müsaitliği appointment_slots'a karşı,
sadece bu daralmış aday havuzunda kontrol edilir. Slot verisi sürekli
değiştiği için Qdrant payload'ına hiç senkronize edilmez (bkz.
docs/roadmap.md tartışması).
"""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AppointmentSlot

TimeOfDay = Literal["morning", "afternoon", "evening"]
TIME_OF_DAY_RANGES: dict[TimeOfDay, tuple[time, time]] = {
    "morning": (time(6, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "evening": (time(17, 0), time(23, 0)),
}


class DateAvailabilityFilter(BaseModel):
    """Belirli bir takvim tarihinde (ve opsiyonel günün bölümünde) müsaitlik kontrolü.

    SearchFilters'tan bilerek ayrı tutulur — Qdrant'a değil appointment_slots
    tablosuna karşı çalışır. Çağıran, bunun diğer filtrelerden farklı/daha
    pahalı bir sorgu tetikleyeceğini bilmeli.
    """

    date: date
    time_of_day: TimeOfDay | None = None


def _availability_time_range(
    availability: DateAvailabilityFilter,
) -> tuple[datetime, datetime]:
    """DateAvailabilityFilter'dan sorgu için (başlangıç, bitiş) datetime aralığını üretir.

    appointment_slots.start_time timezone-aware bir kolon ama generate_slots
    (scripts/synthetic/schedule.py) ve seed_db.py zaten naive datetime
    yazıyor — aynı konvansiyona uyulur, burada yeni bir tzinfo icat edilmez.
    """
    if availability.time_of_day is not None:
        start_time, end_time = TIME_OF_DAY_RANGES[availability.time_of_day]
    else:
        start_time, end_time = time.min, time.max
    return (
        datetime.combine(availability.date, start_time),
        datetime.combine(availability.date, end_time),
    )


async def fetch_available_business_ids(
    session: AsyncSession,
    business_ids: list[int],
    availability: DateAvailabilityFilter,
) -> set[int]:
    """Aday havuzundaki işletmelerden, verilen tarihte/saat diliminde en az
    bir boş (is_booked=false) slotu olanların ID'lerini döner.

    İki fazlı filtrelemenin ikinci fazı: search-service'in aday havuzu
    (RRF sonrası, ~40 işletme) zaten daraltılmış olduğu için appointment_slots
    sorgusu 478 işletmenin tamamını değil sadece bu küçük kümeyi tarar.
    """
    if not business_ids:
        return set()

    start, end = _availability_time_range(availability)
    result = await session.execute(
        select(AppointmentSlot.business_id)
        .where(
            AppointmentSlot.business_id.in_(business_ids),
            AppointmentSlot.start_time >= start,
            AppointmentSlot.start_time < end,
            AppointmentSlot.is_booked.is_(False),
        )
        .distinct()
    )
    return set(result.scalars().all())

"""Entegrasyon testleri için throwaway veri üreten yardımcı fonksiyonlar.

`conftest.py`'ye değil buraya konuldu — bunlar fixture değil, `savepoint_session`
gibi bir session alıp düz Python nesnesi üreten sıradan yardımcı fonksiyonlar.
Birden fazla test dosyası (`test_book.py`, `test_db_query_counts.py`) aynı
şekle (Business/AppointmentSlot/UserProfile minimum zorunlu alanları) ihtiyaç
duyduğu için tek yerden.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AppointmentSlot, Business, UserProfile

DEFAULT_CATEGORY = "Diş Kliniği"


async def create_business(
    session: AsyncSession, *, category: str = DEFAULT_CATEGORY
) -> Business:
    business = Business(
        place_id=f"integration-test-{uuid4()}",
        title="Entegrasyon Test İşletmesi",
        type_normalized=category,
        price_min=100,
        price_max=300,
        appointment_duration_min=30,
        gender="unisex",
    )
    session.add(business)
    await session.flush()
    return business


async def create_slot(
    session: AsyncSession,
    business_id: int,
    start_time: datetime,
    *,
    is_booked: bool = False,
) -> AppointmentSlot:
    slot = AppointmentSlot(
        business_id=business_id, start_time=start_time, is_booked=is_booked
    )
    session.add(slot)
    await session.flush()
    return slot


async def create_user(
    session: AsyncSession, name: str = "Entegrasyon Test Kullanıcısı"
) -> UserProfile:
    user = UserProfile(name=name)
    session.add(user)
    await session.flush()
    return user


def future_start_time(*, days_ahead: int = 3, hour: int = 10) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)

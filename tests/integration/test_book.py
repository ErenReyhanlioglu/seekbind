"""`/book` standart senaryoları için gerçek HTTP entegrasyon testleri.

SAVEPOINT-rollback izolasyonu kullanır (`conftest.py::book_savepoint_client`/
`savepoint_session`) — testin kendi kurduğu throwaway `Business`/
`AppointmentSlot`/`UserProfile` satırları gerçek dev DB'ye yazılır ama
transaction hiç commit edilmeden (dış SAVEPOINT rollback ile) geri alınır,
dev veride hiçbir iz kalmaz. Dev veri şekline bağımlı olmamak için (mevcut
slot/kullanıcı aramak yerine) her senaryo ihtiyacı olan veriyi kendi kurar.

Eşzamanlı/race-condition senaryosu bilerek burada DEĞİL — bkz.
`test_book_concurrency.py` (kökten farklı bir izolasyon mekanizması kullanıyor).
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AppointmentSlot, Booking, Business, UserProfile

pytestmark = pytest.mark.integration

_CATEGORY = "Diş Kliniği"


async def _create_business(session: AsyncSession, *, category: str = _CATEGORY) -> Business:
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


async def _create_slot(session: AsyncSession, business_id: int, start_time: datetime, *, is_booked: bool = False) -> AppointmentSlot:
    slot = AppointmentSlot(business_id=business_id, start_time=start_time, is_booked=is_booked)
    session.add(slot)
    await session.flush()
    return slot


async def _create_user(session: AsyncSession, name: str = "Entegrasyon Test Kullanıcısı") -> UserProfile:
    user = UserProfile(name=name)
    session.add(user)
    await session.flush()
    return user


def _future_start_time(*, days_ahead: int = 3, hour: int = 10) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


async def test_book_succeeds_for_free_slot_without_conflicts(
    book_savepoint_client: httpx.AsyncClient, savepoint_session: AsyncSession
) -> None:
    business = await _create_business(savepoint_session)
    slot = await _create_slot(savepoint_session, business.id, _future_start_time())
    user = await _create_user(savepoint_session)

    response = await book_savepoint_client.post(
        "/book", json={"user_id": user.id, "appointment_slot_id": slot.id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["booking_id"] is not None

    # Gerçekten yazıldı mı — sadece HTTP yanıtına değil, gerçek DB durumuna bak.
    await savepoint_session.refresh(slot)
    assert slot.is_booked is True
    booking = (
        await savepoint_session.execute(select(Booking).where(Booking.appointment_slot_id == slot.id))
    ).scalar_one()
    assert booking.user_id == user.id


async def test_book_returns_alternatives_when_slot_already_booked(
    book_savepoint_client: httpx.AsyncClient, savepoint_session: AsyncSession
) -> None:
    target_business = await _create_business(savepoint_session)
    target_slot = await _create_slot(savepoint_session, target_business.id, _future_start_time(), is_booked=True)
    user = await _create_user(savepoint_session)

    # Aynı kategoride, aynı gün müsait ikinci bir işletme — çapraz-işletme
    # alternatifinin gerçek dev veriye (o günün müsaitliğine) bağımlı
    # kalmadan, deterministik olarak bulunmasını garanti eder.
    alternative_business = await _create_business(savepoint_session)
    await _create_slot(
        savepoint_session, alternative_business.id, _future_start_time(hour=14), is_booked=False
    )

    response = await book_savepoint_client.post(
        "/book", json={"user_id": user.id, "appointment_slot_id": target_slot.id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["booking_id"] is None
    assert len(body["alternatives"]) > 0
    assert any(alt["business"]["id"] == alternative_business.id for alt in body["alternatives"])


async def test_book_returns_alternatives_when_user_has_conflicting_appointment(
    book_savepoint_client: httpx.AsyncClient, savepoint_session: AsyncSession
) -> None:
    user = await _create_user(savepoint_session)

    # Kullanıcının FARKLI bir işletmede zaten sahip olduğu, aynı saat
    # aralığına denk gelen bir randevu (önceden yapılmış bir booking gibi).
    existing_business = await _create_business(savepoint_session)
    conflicting_start = _future_start_time()
    existing_slot = await _create_slot(savepoint_session, existing_business.id, conflicting_start, is_booked=True)
    savepoint_session.add(Booking(user_id=user.id, appointment_slot_id=existing_slot.id))
    await savepoint_session.flush()

    # Aynı zaman aralığında, BAŞKA bir işletmede boş bir slot rezerve etmeye çalış.
    target_business = await _create_business(savepoint_session)
    target_slot = await _create_slot(savepoint_session, target_business.id, conflicting_start, is_booked=False)

    response = await book_savepoint_client.post(
        "/book", json={"user_id": user.id, "appointment_slot_id": target_slot.id}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["booking_id"] is None


async def test_book_returns_404_for_nonexistent_slot(book_savepoint_client: httpx.AsyncClient) -> None:
    response = await book_savepoint_client.post(
        "/book", json={"user_id": 1, "appointment_slot_id": 2_147_483_647}
    )

    assert response.status_code == 404

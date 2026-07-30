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

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Booking
from tests.integration.factories import create_business as _create_business
from tests.integration.factories import create_slot as _create_slot
from tests.integration.factories import create_user as _create_user
from tests.integration.factories import future_start_time as _future_start_time

pytestmark = pytest.mark.integration


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

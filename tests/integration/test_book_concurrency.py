"""`/book` race-condition testi — eşzamanlı 10 istek aynı slotu kapmaya çalışıyor.

Bu dosya BİLEREK `test_book.py`'den ayrı ve kökten farklı bir izolasyon
mekanizması kullanıyor: SAVEPOINT-rollback (test_book.py) tek bir session/
connection üzerinden çalışır — asyncpg aynı connection'da eşzamanlı sorguya
izin vermez (ya hata verir ya sıralar), yani orada gerçek bir yarış hiç
oluşamaz. Bu testin amacı tam olarak `_claim_slot`'un
(backend/services/calendar.py — atomik `UPDATE ... WHERE is_booked=false`)
GERÇEKTEN eşzamanlı, BAĞIMSIZ connection'lar altında doğru davrandığını
kanıtlamak — bu yüzden override'sız gerçek `get_db_session` kullanılıyor
(her istek connection pool'dan kendi bağımsız connection'ını alır) ve gerçek
commit atılıyor. 10 farklı throwaway kullanıcı kullanılıyor ki "aynı
kullanıcı kendi randevusuyla çakışıyor" iş kuralı (bkz. test_book.py'deki
ayrı test), `_claim_slot`'un atomikliğini izole etme amacını bulandırmasın.

Testin kendi oluşturduğu satırlar `finally` bloğunda elle silinir — test
ortasında bir hata fırlarsa bile dev DB'de çöp veri kalmaz.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from backend.db.models import AppointmentSlot, Booking, Business, UserProfile
from backend.db.session import get_session_factory

pytestmark = pytest.mark.integration

_CONCURRENT_REQUEST_COUNT = 10


async def test_book_allows_exactly_one_winner_under_concurrent_requests(api_client: httpx.AsyncClient) -> None:
    session_factory = get_session_factory()

    async with session_factory() as setup_session:
        business = Business(
            place_id=f"integration-concurrency-{uuid4()}",
            title="Eşzamanlılık Test İşletmesi",
            type_normalized="Diş Kliniği",
            price_min=100,
            price_max=300,
            appointment_duration_min=30,
            gender="unisex",
        )
        setup_session.add(business)
        await setup_session.flush()

        slot = AppointmentSlot(
            business_id=business.id,
            start_time=datetime.now(timezone.utc) + timedelta(days=5),
            is_booked=False,
        )
        setup_session.add(slot)
        await setup_session.flush()

        users = [UserProfile(name=f"Eşzamanlılık Test Kullanıcısı {i}") for i in range(_CONCURRENT_REQUEST_COUNT)]
        setup_session.add_all(users)
        await setup_session.flush()

        business_id = business.id
        slot_id = slot.id
        user_ids = [user.id for user in users]

        await setup_session.commit()

    try:
        responses = await asyncio.gather(
            *(
                api_client.post("/book", json={"user_id": user_id, "appointment_slot_id": slot_id})
                for user_id in user_ids
            )
        )

        assert all(response.status_code == 200 for response in responses)
        bodies = [response.json() for response in responses]
        successes = [body for body in bodies if body["success"] is True]
        failures = [body for body in bodies if body["success"] is False]

        # Bu proje "slot dolu" durumunu 409/400 değil, yapılandırılmış bir
        # 200 yanıtıyla temsil ediyor (bkz. schemas.py::BookResponse, ADR-0018)
        # — bu yüzden ayırt edici sinyal status code değil, `success` alanı.
        assert len(successes) == 1
        assert len(failures) == _CONCURRENT_REQUEST_COUNT - 1
        assert successes[0]["booking_id"] is not None
        assert all(failure["booking_id"] is None for failure in failures)
    finally:
        async with session_factory() as cleanup_session:
            await cleanup_session.execute(delete(Booking).where(Booking.appointment_slot_id == slot_id))
            await cleanup_session.execute(delete(AppointmentSlot).where(AppointmentSlot.id == slot_id))
            await cleanup_session.execute(delete(Business).where(Business.id == business_id))
            await cleanup_session.execute(delete(UserProfile).where(UserProfile.id.in_(user_ids)))
            await cleanup_session.commit()

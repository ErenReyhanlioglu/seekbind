"""Referans bir test kullanıcı profili oluşturur ve farklı işletmelerden
birkaç gerçek (zaten is_booked=true) randevu slotunu bu kullanıcıya
Booking ile bağlar.

Truncate-and-load mantığıyla çalışır (idempotent, tekrar çalıştırılabilir):
önce bu script'in daha önce oluşturduğu test kullanıcısını (cascade ile
bookinglerini de) siler, sonra baştan oluşturur — seed_db.py'nin
appointment_slots için kullandığı aynı desen.

Not: seed_db.py'ye dahil edilmedi — o gerçek SerpAPI verisini yüklüyor,
bu ise sentetik/test amaçlı bir referans kullanıcı, farklı bir kaygı.
"""

import asyncio
import logging

from sqlalchemy import delete, select

from backend.db.models import AppointmentSlot, Booking, UserProfile
from backend.db.session import get_session_factory

logger = logging.getLogger(__name__)

TEST_USER_NAME: str = "Test Kullanıcı"
# 478 işletmenin ortalama konumu (bkz. proje notları) — gerçek bir
# kullanıcı adresi değil, bilinçli seçilmiş bir referans/test noktası.
REFERENCE_LATITUDE: float = 40.7560
REFERENCE_LONGITUDE: float = 29.9734
TEST_BOOKING_COUNT: int = 5


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            await session.execute(delete(UserProfile).where(UserProfile.name == TEST_USER_NAME))

            user = UserProfile(name=TEST_USER_NAME, latitude=REFERENCE_LATITUDE, longitude=REFERENCE_LONGITUDE)
            session.add(user)
            await session.flush()  # Booking'lerde kullanmak için user.id gerekiyor

            # Farklı işletmelerden birer dolu slot seçiliyor (DISTINCT ON) —
            # test kullanıcısının "günü" tek bir işletmeye sıkışmasın diye,
            # ileride calendar-service'in çakışma kontrolünü anlamlı test
            # edebilmesi için.
            result = await session.execute(
                select(AppointmentSlot.id)
                .distinct(AppointmentSlot.business_id)
                .where(AppointmentSlot.is_booked.is_(True))
                .order_by(AppointmentSlot.business_id, AppointmentSlot.start_time)
                .limit(TEST_BOOKING_COUNT)
            )
            slot_ids = result.scalars().all()

            session.add_all([Booking(user_id=user.id, appointment_slot_id=slot_id) for slot_id in slot_ids])
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    logger.info("Test kullanıcı '%s' oluşturuldu, %d randevuya bağlandı", TEST_USER_NAME, len(slot_ids))


if __name__ == "__main__":
    asyncio.run(main())

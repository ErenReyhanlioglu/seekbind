"""Randevu rezervasyonu — belirli bir slotu kullanıcıya bağlama.

`search/availability.py`'nin tamamlayıcısı: o "bu işletmede o gün/saatte
HERHANGİ bir boş slot var mı" (arama/filtreleme, salt okuma) sorusuna
cevap veriyor; burası "BELİRLİ bir slotu BELİRLİ bir kullanıcıya rezerve
edebilir miyim" (yazma/eylem) sorusunu çözüyor — kullanıcının kendi
randevularıyla çakışma kontrolü dahil.

Müsait değilse (slot dolu ya da kullanıcının başka bir randevusuyla
çakışıyor) yapılandırılmış alternatif önerisi döner — düz metin değil,
çünkü ileride bunu programatik tüketecek bir orkestrasyon katmanı
(bkz. docs/roadmap.md "SeekBind 2.0" notu) için tasarlandı. Alternatifler
iki kaynaktan gelir: (1) aynı işletmenin başka bir zamanı (kronolojik
sıralanır — puan sabit olduğu için sıralamada ayırt edici değil), (2)
aynı kategorideki, aynı gün müsait olan başka işletmeler (weighted_rating'e
göre sıralanır — burada puan gerçekten ayırt edici, `search/service.py`'nin
`_sort_by_rating`'iyle aynı NULL-son deseni kullanılır, bkz. ADR-0015).

Mesafe bilinçli olarak dışarıda bırakıldı — ayrı bir mini branch'te ele
alınacak (bkz. docs/roadmap.md).
"""

from datetime import date, datetime, time, timedelta
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import BookingAlternative, BookResponse
from backend.db.models import AppointmentSlot, Booking, Business
from backend.services.search.availability import DateAvailabilityFilter, fetch_available_business_ids

ALTERNATIVE_LIMIT: int = 5


class CalendarServiceError(Exception):
    """Randevu servisi işlemi başarısız olduğunda fırlatılır."""


class SlotNotFoundError(CalendarServiceError):
    """Verilen appointment_slot_id'ye karşılık gelen bir slot yoksa."""


async def _fetch_slot(
    session: AsyncSession, appointment_slot_id: int
) -> tuple[int, str, datetime, int, bool] | None:
    """(business_id, kategori, start_time, randevu_süresi_dk, is_booked) döner, yoksa None."""
    result = await session.execute(
        select(
            AppointmentSlot.business_id,
            Business.type_normalized,
            AppointmentSlot.start_time,
            Business.appointment_duration_min,
            AppointmentSlot.is_booked,
        )
        .join(Business, AppointmentSlot.business_id == Business.id)
        .where(AppointmentSlot.id == appointment_slot_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    return row[0], row[1], row[2], row[3], row[4]


def _slots_overlap(start_a: datetime, duration_a: int, start_b: datetime, duration_b: int) -> bool:
    """İki randevu süresinin (kendi süreleri kadar) zaman olarak çakışıp çakışmadığını kontrol eder."""
    end_a = start_a + timedelta(minutes=duration_a)
    end_b = start_b + timedelta(minutes=duration_b)
    return start_a < end_b and start_b < end_a


async def _fetch_user_schedule(session: AsyncSession, user_id: int) -> list[tuple[datetime, int]]:
    """Kullanıcının mevcut tüm rezervasyonlarının (başlangıç, süre) listesini döner."""
    result = await session.execute(
        select(AppointmentSlot.start_time, Business.appointment_duration_min)
        .join(Booking, Booking.appointment_slot_id == AppointmentSlot.id)
        .join(Business, AppointmentSlot.business_id == Business.id)
        .where(Booking.user_id == user_id)
    )
    return [(row[0], row[1]) for row in result.all()]


async def _has_user_conflict(
    session: AsyncSession, user_id: int, candidate_start: datetime, candidate_duration: int
) -> bool:
    """Verilen aday slotun, kullanıcının mevcut randevularından biriyle çakışıp çakışmadığını kontrol eder."""
    schedule = await _fetch_user_schedule(session, user_id)
    return any(_slots_overlap(candidate_start, candidate_duration, start, duration) for start, duration in schedule)


async def _find_same_business_alternatives(
    session: AsyncSession, user_id: int, business_id: int, exclude_slot_id: int
) -> list[BookingAlternative]:
    """Aynı işletmedeki, kullanıcının programıyla çakışmayan boş slotlardan
    öneri üretir — kronolojik sıralanır (puan sabit, ayırt edici değil)."""
    result = await session.execute(
        select(AppointmentSlot.id, AppointmentSlot.start_time, Business.title, Business.appointment_duration_min)
        .join(Business, AppointmentSlot.business_id == Business.id)
        .where(
            AppointmentSlot.business_id == business_id,
            AppointmentSlot.is_booked.is_(False),
            AppointmentSlot.id != exclude_slot_id,
        )
        .order_by(AppointmentSlot.start_time)
    )
    schedule = await _fetch_user_schedule(session, user_id)

    alternatives: list[BookingAlternative] = []
    for slot_id, start_time, title, duration in result.all():
        if any(_slots_overlap(start_time, duration, s, d) for s, d in schedule):
            continue
        alternatives.append(
            BookingAlternative(
                business_id=business_id, business_title=title, appointment_slot_id=slot_id, start_time=start_time
            )
        )
        if len(alternatives) >= ALTERNATIVE_LIMIT:
            break
    return alternatives


async def _same_category_candidate_ids(
    session: AsyncSession,
    exclude_business_id: int,
    category: str,
    online_only: bool,
    gender: str | None,
    min_price: int | None,
    max_price: int | None,
) -> list[int]:
    """Aynı kategorideki, verilen kısıtlara uyan (orijinal işletme hariç) aktif işletme ID'lerini döner.

    Fiyat, `search/filters.py`'deki AYNI aralık örtüşmesi mantığıyla
    kontrol edilir — kullanıcının bütçesiyle işletmenin fiyat aralığının
    kesişip kesişmediğine bakılır.
    """
    conditions = [
        Business.type_normalized == category,
        Business.id != exclude_business_id,
        Business.is_active.is_(True),
    ]
    if online_only:
        conditions.append(Business.online_available.is_(True))
    if gender is not None:
        conditions.append(Business.gender == gender)
    if max_price is not None:
        conditions.append(Business.price_min <= max_price)
    if min_price is not None:
        conditions.append(Business.price_max >= min_price)

    result = await session.execute(select(Business.id).where(*conditions))
    return list(result.scalars().all())


async def _find_cross_business_alternatives(
    session: AsyncSession,
    user_id: int,
    original_business_id: int,
    category: str,
    target_date: date,
    online_only: bool,
    gender: str | None,
    min_price: int | None,
    max_price: int | None,
) -> list[BookingAlternative]:
    """Aynı kategorideki diğer işletmelerden, verilen kısıtlara uyan ve aynı
    gün müsait olan alternatifler bulur. Her işletmeden en erken boş slot
    alınır (çeşitlilik için tek işletme birden fazla kez önerilmez),
    weighted_rating'e göre sıralanır — puanı olmayanlar (ADR-0004'teki
    Bayesian düzeltme az yorumlu işletmelerde None kalabiliyor) yön fark
    etmeksizin sona eklenir (bkz. ADR-0015'teki aynı desen).
    """
    candidate_ids = await _same_category_candidate_ids(
        session, original_business_id, category, online_only, gender, min_price, max_price
    )
    if not candidate_ids:
        return []

    available_ids = await fetch_available_business_ids(
        session, candidate_ids, DateAvailabilityFilter(date=target_date)
    )
    if not available_ids:
        return []

    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)
    result = await session.execute(
        select(
            AppointmentSlot.id,
            AppointmentSlot.business_id,
            AppointmentSlot.start_time,
            Business.title,
            Business.appointment_duration_min,
            Business.weighted_rating,
        )
        .join(Business, AppointmentSlot.business_id == Business.id)
        .where(
            AppointmentSlot.business_id.in_(available_ids),
            AppointmentSlot.is_booked.is_(False),
            AppointmentSlot.start_time >= day_start,
            AppointmentSlot.start_time < day_end,
        )
        .order_by(AppointmentSlot.business_id, AppointmentSlot.start_time)
    )
    schedule = await _fetch_user_schedule(session, user_id)

    best_per_business: dict[int, BookingAlternative] = {}
    for slot_id, business_id, start_time, title, duration, rating in result.all():
        if business_id in best_per_business:
            continue  # bu işletmeden zaten (en erken olduğu için ilk görülen) bir slot seçildi
        if any(_slots_overlap(start_time, duration, s, d) for s, d in schedule):
            continue
        best_per_business[business_id] = BookingAlternative(
            business_id=business_id,
            business_title=title,
            appointment_slot_id=slot_id,
            start_time=start_time,
            weighted_rating=rating,
        )

    rated = [alt for alt in best_per_business.values() if alt.weighted_rating is not None]
    unrated = [alt for alt in best_per_business.values() if alt.weighted_rating is None]
    rated.sort(key=lambda alt: cast(float, alt.weighted_rating), reverse=True)
    return (rated + unrated)[:ALTERNATIVE_LIMIT]


async def _find_alternatives(
    session: AsyncSession,
    user_id: int,
    business_id: int,
    category: str,
    exclude_slot_id: int,
    requested_start: datetime,
    online_only: bool,
    gender: str | None,
    min_price: int | None,
    max_price: int | None,
) -> list[BookingAlternative]:
    """Aynı kategorideki diğer işletmeleri (aynı gün, puana göre sıralı) +
    aynı işletmenin başka zamanlarını (kronolojik) birleştirip döner —
    ilki önce, çünkü orijinal istek genellikle günü sabit tutmak istiyor.
    """
    cross_business = await _find_cross_business_alternatives(
        session, user_id, business_id, category, requested_start.date(), online_only, gender, min_price, max_price
    )
    same_business = await _find_same_business_alternatives(session, user_id, business_id, exclude_slot_id)
    return (cross_business + same_business)[:ALTERNATIVE_LIMIT]


async def _claim_slot(session: AsyncSession, appointment_slot_id: int) -> bool:
    """Slotu atomik olarak (is_booked=false koşuluyla) rezerve eder.

    İki farklı isteğin aynı slotu aynı anda kapmaya çalışmasına karşı —
    tek bir UPDATE ... WHERE is_booked=false ile, ayrı bir SELECT +
    UPDATE arasında oluşabilecek yarış durumunu (race condition) önler.
    """
    result = await session.execute(
        update(AppointmentSlot)
        .where(AppointmentSlot.id == appointment_slot_id, AppointmentSlot.is_booked.is_(False))
        .values(is_booked=True)
    )
    # AsyncSession.execute()'ün dönüş tipi Pyright için genel Result[Any] —
    # ama bu bir UPDATE olduğu için gerçekte her zaman rowcount destekleyen
    # bir CursorResult döner.
    return cast(CursorResult, result).rowcount > 0


async def book_appointment(
    session: AsyncSession,
    user_id: int,
    appointment_slot_id: int,
    online_only: bool = False,
    gender: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
) -> BookResponse:
    """Belirli bir randevu slotunu kullanıcıya rezerve etmeyi dener.

    Sırayla: slot var mı (yoksa `SlotNotFoundError`) -> slot zaten dolu mu
    ya da kullanıcının başka bir randevusuyla çakışıyor mu (biri
    doğruysa alternatif öner) -> atomik olarak rezerve etmeyi dene (araya
    başka biri girdiyse yine alternatif öner) -> `Booking` kaydı oluştur.

    `online_only`/`gender`/`min_price`/`max_price` opsiyonel — çağıran
    orijinal `/recommend` isteğinden bu tercihleri biliyorsa, alternatif
    önerisinin de bunlara uymasını istiyorsa iletebilir.
    """
    slot = await _fetch_slot(session, appointment_slot_id)
    if slot is None:
        raise SlotNotFoundError(f"appointment_slot_id={appointment_slot_id} bulunamadı")

    business_id, category, start_time, duration_min, is_booked = slot
    if is_booked or await _has_user_conflict(session, user_id, start_time, duration_min):
        alternatives = await _find_alternatives(
            session, user_id, business_id, category, appointment_slot_id, start_time,
            online_only, gender, min_price, max_price,
        )
        return BookResponse(success=False, alternatives=alternatives)

    if not await _claim_slot(session, appointment_slot_id):
        alternatives = await _find_alternatives(
            session, user_id, business_id, category, appointment_slot_id, start_time,
            online_only, gender, min_price, max_price,
        )
        return BookResponse(success=False, alternatives=alternatives)

    booking = Booking(user_id=user_id, appointment_slot_id=appointment_slot_id)
    session.add(booking)
    await session.flush()
    return BookResponse(success=True, booking_id=booking.id)

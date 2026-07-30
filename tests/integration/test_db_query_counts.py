"""N+1 regresyon testleri — gerçek SQL sorgu sayısının veri boyutundan
bağımsız (O(1)) olduğunu kanıtlar.

Yöntem: her karşılaştırmalı test aynı fonksiyonu küçük (N) ve büyük (10×N)
bir veri kümesiyle çalıştırıp sorgu sayısının birebir eşit çıktığını doğrular
— tek noktalı bir üst sınır ("sorgu sayısı ≤ 3") değil, sorgu sayısının veri
boyutundan bağımsız olduğunun kanıtı. Sabit boyutlu fonksiyonlar için ("her
zaman tam 1 sorgu") tek ölçüm yeterli.

`search_providers()` burada DOĞRUDAN test edilmiyor — Qdrant ve BM25,
`savepoint_session`'ın commit edilmemiş throwaway verisini göremiyor (ayrı
bağlantı/session), yani "N throwaway işletme ekle" deseni onun asıl aday
havuzunu kontrol etmiyor. Bunun yerine `search_providers()`'ın gerçek (session
üzerinden giden) tek adımı olan `_fetch_businesses_by_id` doğrudan, gerçek
(salt okunan, riski olmayan) dev veriyle test ediliyor. `book_appointment()`
ise tamamen session-tabanlı (Qdrant/BM25'e hiç dokunmuyor) olduğu için
throwaway veri + karşılaştırmalı ölçüm burada tam olarak işliyor.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from backend.services.calendar import book_appointment
from backend.services.rag.pricing import resolve_price_threshold
from backend.services.search.availability import DateAvailabilityFilter, fetch_available_business_ids
from backend.services.search.service import _fetch_businesses_by_id
from tests.integration.factories import DEFAULT_CATEGORY, create_business, create_slot, create_user, future_start_time

pytestmark = pytest.mark.integration

_SMALL_N = 5
_LARGE_N = 50


async def _real_business_ids(session: AsyncSession, limit: int) -> list[int]:
    """Gerçek dev DB'den (salt okuma) var olan işletme id'lerini döner."""
    result = await session.execute(select(Business.id).limit(limit))
    return list(result.scalars().all())


async def test_fetch_businesses_by_id_issues_single_query_regardless_of_batch_size(
    savepoint_session: AsyncSession, query_counter: list[str]
) -> None:
    ids = await _real_business_ids(savepoint_session, _LARGE_N)
    assert len(ids) >= _LARGE_N, "dev DB'de karşılaştırma için yeterli işletme yok"

    query_counter.clear()
    await _fetch_businesses_by_id(savepoint_session, ids[:_SMALL_N])
    small_count = len(query_counter)

    query_counter.clear()
    await _fetch_businesses_by_id(savepoint_session, ids[:_LARGE_N])
    large_count = len(query_counter)

    assert small_count == 1
    assert large_count == 1


async def test_fetch_available_business_ids_issues_single_query(
    savepoint_session: AsyncSession, query_counter: list[str]
) -> None:
    ids = await _real_business_ids(savepoint_session, _LARGE_N)
    assert len(ids) >= _LARGE_N, "dev DB'de karşılaştırma için yeterli işletme yok"
    availability = DateAvailabilityFilter(date=date.today() + timedelta(days=60))

    query_counter.clear()
    await fetch_available_business_ids(savepoint_session, ids[:_SMALL_N], availability)
    small_count = len(query_counter)

    query_counter.clear()
    await fetch_available_business_ids(savepoint_session, ids[:_LARGE_N], availability)
    large_count = len(query_counter)

    assert small_count == 1
    assert large_count == 1


async def test_resolve_price_threshold_issues_single_query(
    savepoint_session: AsyncSession, query_counter: list[str]
) -> None:
    query_counter.clear()
    await resolve_price_threshold(savepoint_session, DEFAULT_CATEGORY, "cheap")

    assert len(query_counter) == 1


async def test_book_appointment_alternative_search_query_count_independent_of_candidate_count(
    savepoint_session: AsyncSession, query_counter: list[str]
) -> None:
    """`book_appointment()`'ın alternatif bulma yolu (`_find_alternatives` ->
    `_find_cross_business_alternatives` + `_find_same_business_alternatives`),
    aynı kategoride kaç aday işletme müsait olursa olsun aynı sayıda sorgu
    çalıştırmalı — adayların hepsi tek bir `IN (...)` sorgusuna gidiyor,
    aday başına ayrı bir sorguya değil (bkz. calendar.py)."""
    target_business = await create_business(savepoint_session)
    target_slot = await create_slot(savepoint_session, target_business.id, future_start_time(), is_booked=True)
    user = await create_user(savepoint_session)

    async def _add_candidates(count: int) -> None:
        for _ in range(count):
            business = await create_business(savepoint_session)
            await create_slot(savepoint_session, business.id, future_start_time(hour=14), is_booked=False)

    await _add_candidates(_SMALL_N)
    query_counter.clear()
    await book_appointment(savepoint_session, user.id, target_slot.id)
    small_count = len(query_counter)

    # Aynı transaction içinde daha fazla aday ekleyip AYNI (hâlâ dolu) slotu
    # tekrar rezerve etmeyi dene — book_appointment dolu slotta hiçbir yazma
    # yapmadan alternatif döner, bu yüzden ikinci çağrı güvenli/yan etkisiz.
    await _add_candidates(_LARGE_N - _SMALL_N)
    query_counter.clear()
    await book_appointment(savepoint_session, user.id, target_slot.id)
    large_count = len(query_counter)

    assert small_count == large_count

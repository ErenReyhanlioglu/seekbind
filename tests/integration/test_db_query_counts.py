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
üzerinden giden) tek adımı olan `_fetch_businesses_by_id` doğrudan test
ediliyor. `_fetch_businesses_by_id`/`fetch_available_business_ids`'in kendisi
düz bir `WHERE id IN (...)` sorgusu (ilişki yüklemesi yok, işletme içeriğine
bakmıyor) olduğu için sorgu sayısı ID'lerin gerçek/throwaway olmasından
bağımsız — bu yüzden throwaway işletme (`create_business`) burada da
`book_appointment()`'daki gibi güvenle kullanılıyor, CI'da (dev DB seed'siz)
de anlamlı kalıyor.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.calendar import book_appointment
from backend.services.rag.pricing import resolve_price_threshold
from backend.services.search.availability import (
    DateAvailabilityFilter,
    fetch_available_business_ids,
)
from backend.services.search.service import _fetch_businesses_by_id
from tests.integration.factories import (
    DEFAULT_CATEGORY,
    create_business,
    create_slot,
    create_user,
    future_start_time,
)

pytestmark = pytest.mark.integration

_SMALL_N = 5
_LARGE_N = 50


async def _create_throwaway_business_ids(
    session: AsyncSession, count: int
) -> list[int]:
    """`count` kadar throwaway işletme oluşturup ID'lerini döner.

    `_fetch_businesses_by_id`/`fetch_available_business_ids` düz bir
    `WHERE id IN (...)` sorgusu (bkz. dosya docstring'i) — gerçek/throwaway
    ayrımı sorgu sayısını etkilemiyor.
    """
    return [(await create_business(session)).id for _ in range(count)]


async def test_fetch_businesses_by_id_issues_single_query_regardless_of_batch_size(
    savepoint_session: AsyncSession, query_counter: list[str]
) -> None:
    ids = await _create_throwaway_business_ids(savepoint_session, _LARGE_N)

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
    ids = await _create_throwaway_business_ids(savepoint_session, _LARGE_N)
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
    target_slot = await create_slot(
        savepoint_session, target_business.id, future_start_time(), is_booked=True
    )
    user = await create_user(savepoint_session)

    async def _add_candidates(count: int) -> None:
        for _ in range(count):
            business = await create_business(savepoint_session)
            await create_slot(
                savepoint_session,
                business.id,
                future_start_time(hour=14),
                is_booked=False,
            )

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

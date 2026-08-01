"""backend/services/search/availability.py için birim testler."""

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.search.availability import (
    DateAvailabilityFilter,
    _availability_time_range,
    fetch_available_business_ids,
)


def test_availability_time_range_uses_morning_boundaries() -> None:
    availability = DateAvailabilityFilter(date=date(2026, 8, 12), time_of_day="morning")

    start, end = _availability_time_range(availability)

    assert start == datetime(2026, 8, 12, 6, 0)
    assert end == datetime(2026, 8, 12, 12, 0)


def test_availability_time_range_covers_full_day_when_time_of_day_not_given() -> None:
    availability = DateAvailabilityFilter(date=date(2026, 8, 12))

    start, end = _availability_time_range(availability)

    assert start == datetime.combine(date(2026, 8, 12), time.min)
    assert end == datetime.combine(date(2026, 8, 12), time.max)


def test_availability_time_range_evening_does_not_overlap_afternoon() -> None:
    afternoon = DateAvailabilityFilter(date=date(2026, 8, 12), time_of_day="afternoon")
    evening = DateAvailabilityFilter(date=date(2026, 8, 12), time_of_day="evening")

    _, afternoon_end = _availability_time_range(afternoon)
    evening_start, _ = _availability_time_range(evening)

    assert afternoon_end == evening_start


async def test_fetch_available_business_ids_returns_empty_set_for_empty_candidate_list() -> (
    None
):
    """Aday havuzu boşsa DB'ye hiç gidilmemeli — appointment_slots'a karşı
    boş bir IN (...) sorgusu atmanın anlamı yok."""
    session = AsyncMock()

    result = await fetch_available_business_ids(
        session, [], DateAvailabilityFilter(date=date(2026, 8, 12))
    )

    assert result == set()
    session.execute.assert_not_called()


async def test_fetch_available_business_ids_returns_ids_with_open_slots() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [3, 7])
    )

    result = await fetch_available_business_ids(
        session,
        [3, 5, 7],
        DateAvailabilityFilter(date=date(2026, 8, 12), time_of_day="morning"),
    )

    assert result == {3, 7}

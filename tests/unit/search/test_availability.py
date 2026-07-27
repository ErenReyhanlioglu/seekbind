"""backend/services/search/availability.py için birim testler."""

from datetime import date, datetime, time

from backend.services.search.availability import DateAvailabilityFilter, _availability_time_range


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

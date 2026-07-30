"""backend/services/calendar.py için birim testler."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.services.calendar as calendar_module
from backend.api.schemas import BookingAlternative
from backend.services.calendar import (
    ALTERNATIVE_LIMIT,
    SlotNotFoundError,
    _claim_slot,
    _fetch_slot,
    _fetch_user_schedule,
    _find_alternatives,
    _find_cross_business_alternatives,
    _find_same_business_alternatives,
    _has_user_conflict,
    _same_category_candidate_ids,
    _slots_overlap,
    book_appointment,
)


def _make_alternative(appointment_slot_id: int = 1, weighted_rating: float | None = 4.5) -> BookingAlternative:
    return BookingAlternative(
        business_id=5,
        business_title="Test İşletme",
        appointment_slot_id=appointment_slot_id,
        start_time=datetime(2026, 8, 1, 10, 0),
        weighted_rating=weighted_rating,
    )


def test_slots_overlap_detects_overlapping_ranges() -> None:
    start_a = datetime(2026, 8, 1, 10, 0)
    start_b = datetime(2026, 8, 1, 10, 15)

    assert _slots_overlap(start_a, 30, start_b, 30) is True


def test_slots_overlap_returns_false_for_back_to_back_slots() -> None:
    """a bitir bitmez b başlıyor — çakışma yok, tam sınırda dokunma yeterli."""
    start_a = datetime(2026, 8, 1, 10, 0)
    start_b = datetime(2026, 8, 1, 10, 30)

    assert _slots_overlap(start_a, 30, start_b, 30) is False


def test_slots_overlap_returns_false_for_fully_separate_slots() -> None:
    start_a = datetime(2026, 8, 1, 10, 0)
    start_b = datetime(2026, 8, 1, 14, 0)

    assert _slots_overlap(start_a, 30, start_b, 30) is False


def test_slots_overlap_detects_one_slot_fully_containing_another() -> None:
    start_a = datetime(2026, 8, 1, 10, 0)
    start_b = datetime(2026, 8, 1, 10, 5)

    assert _slots_overlap(start_a, 60, start_b, 10) is True


async def test_fetch_slot_returns_none_when_not_found() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(one_or_none=lambda: None)

    result = await _fetch_slot(session, 999)

    assert result is None


async def test_fetch_slot_returns_tuple_when_found() -> None:
    session = AsyncMock()
    now = datetime(2026, 8, 1, 10, 0)
    session.execute.return_value = SimpleNamespace(one_or_none=lambda: (5, "Berber", now, 30, False))

    result = await _fetch_slot(session, 1)

    assert result == (5, "Berber", now, 30, False)


async def test_fetch_user_schedule_returns_start_time_and_duration_pairs() -> None:
    session = AsyncMock()
    now = datetime(2026, 8, 1, 9, 0)
    session.execute.return_value = SimpleNamespace(all=lambda: [(now, 30), (now, 45)])

    schedule = await _fetch_user_schedule(session, user_id=1)

    assert schedule == [(now, 30), (now, 45)]


async def test_has_user_conflict_returns_true_when_overlapping(monkeypatch) -> None:
    existing_start = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[(existing_start, 30)]))

    conflict = await _has_user_conflict(
        AsyncMock(), user_id=1, candidate_start=datetime(2026, 8, 1, 10, 15), candidate_duration=30
    )

    assert conflict is True


async def test_has_user_conflict_returns_false_when_no_overlap(monkeypatch) -> None:
    existing_start = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[(existing_start, 30)]))

    conflict = await _has_user_conflict(
        AsyncMock(), user_id=1, candidate_start=datetime(2026, 8, 1, 14, 0), candidate_duration=30
    )

    assert conflict is False


async def test_find_same_business_alternatives_excludes_slots_conflicting_with_user_schedule(monkeypatch) -> None:
    session = AsyncMock()
    conflicting_time = datetime(2026, 8, 1, 10, 0)
    free_time = datetime(2026, 8, 1, 14, 0)
    session.execute.return_value = SimpleNamespace(
        all=lambda: [
            (10, conflicting_time, "İşletme A", 30),
            (11, free_time, "İşletme A", 30),
        ]
    )
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[(conflicting_time, 30)]))

    alternatives = await _find_same_business_alternatives(session, user_id=1, business_id=5, exclude_slot_id=99)

    assert len(alternatives) == 1
    assert alternatives[0].appointment_slot_id == 11


async def test_find_same_business_alternatives_respects_limit(monkeypatch) -> None:
    session = AsyncMock()
    rows = [(i, datetime(2026, 8, 1, 9 + i, 0), "İşletme A", 30) for i in range(10)]
    session.execute.return_value = SimpleNamespace(all=lambda: rows)
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[]))

    alternatives = await _find_same_business_alternatives(session, user_id=1, business_id=5, exclude_slot_id=99)

    assert len(alternatives) == ALTERNATIVE_LIMIT


async def test_same_category_candidate_ids_applies_all_filters() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [7, 8]))

    result = await _same_category_candidate_ids(
        session,
        exclude_business_id=5,
        category="Berber",
        online_only=True,
        gender="unisex",
        min_price=100,
        max_price=500,
    )

    assert result == [7, 8]
    # Sorgunun gerçekten filtrelerle kurulduğunu (WHERE'e girenler) doğrula
    executed_statement = str(session.execute.call_args.args[0])
    assert "type_normalized" in executed_statement
    assert "online_available" in executed_statement
    assert "gender" in executed_statement
    assert "price_min" in executed_statement
    assert "price_max" in executed_statement


async def test_find_cross_business_alternatives_returns_empty_when_no_candidates(monkeypatch) -> None:
    monkeypatch.setattr(calendar_module, "_same_category_candidate_ids", AsyncMock(return_value=[]))

    alternatives = await _find_cross_business_alternatives(
        AsyncMock(),
        user_id=1,
        original_business_id=5,
        category="Berber",
        target_date=date(2026, 8, 1),
        online_only=False,
        gender=None,
        min_price=None,
        max_price=None,
    )

    assert alternatives == []


async def test_find_cross_business_alternatives_returns_empty_when_none_available(monkeypatch) -> None:
    monkeypatch.setattr(calendar_module, "_same_category_candidate_ids", AsyncMock(return_value=[7, 8]))
    monkeypatch.setattr(calendar_module, "fetch_available_business_ids", AsyncMock(return_value=set()))

    alternatives = await _find_cross_business_alternatives(
        AsyncMock(),
        user_id=1,
        original_business_id=5,
        category="Berber",
        target_date=date(2026, 8, 1),
        online_only=False,
        gender=None,
        min_price=None,
        max_price=None,
    )

    assert alternatives == []


async def test_find_cross_business_alternatives_picks_one_slot_per_business_sorted_by_rating(monkeypatch) -> None:
    """Puanlı işletmeler puana göre (en yüksekten) sıralanır, puansız
    işletme (None) yön fark etmeksizin sona eklenir (bkz. ADR-0015)."""
    monkeypatch.setattr(calendar_module, "_same_category_candidate_ids", AsyncMock(return_value=[7, 8, 9]))
    monkeypatch.setattr(calendar_module, "fetch_available_business_ids", AsyncMock(return_value={7, 8, 9}))
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        all=lambda: [
            # business 7: iki slot var, en erken olan (09:00) seçilmeli
            (701, 7, datetime(2026, 8, 1, 9, 0), "İşletme 7", 30, 4.5),
            (702, 7, datetime(2026, 8, 1, 11, 0), "İşletme 7", 30, 4.5),
            (801, 8, datetime(2026, 8, 1, 10, 0), "İşletme 8", 30, 4.9),
            (901, 9, datetime(2026, 8, 1, 10, 0), "İşletme 9", 30, None),
        ]
    )
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[]))

    alternatives = await _find_cross_business_alternatives(
        session,
        user_id=1,
        original_business_id=5,
        category="Berber",
        target_date=date(2026, 8, 1),
        online_only=False,
        gender=None,
        min_price=None,
        max_price=None,
    )

    assert [alt.appointment_slot_id for alt in alternatives] == [801, 701, 901]


async def test_find_cross_business_alternatives_excludes_user_conflicts(monkeypatch) -> None:
    monkeypatch.setattr(calendar_module, "_same_category_candidate_ids", AsyncMock(return_value=[7]))
    monkeypatch.setattr(calendar_module, "fetch_available_business_ids", AsyncMock(return_value={7}))
    conflicting_time = datetime(2026, 8, 1, 10, 0)
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(
        all=lambda: [(701, 7, conflicting_time, "İşletme 7", 30, 4.5)]
    )
    monkeypatch.setattr(calendar_module, "_fetch_user_schedule", AsyncMock(return_value=[(conflicting_time, 30)]))

    alternatives = await _find_cross_business_alternatives(
        session,
        user_id=1,
        original_business_id=5,
        category="Berber",
        target_date=date(2026, 8, 1),
        online_only=False,
        gender=None,
        min_price=None,
        max_price=None,
    )

    assert alternatives == []


async def test_find_alternatives_puts_cross_business_before_same_business(monkeypatch) -> None:
    cross = [_make_alternative(appointment_slot_id=1)]
    same = [_make_alternative(appointment_slot_id=2)]
    monkeypatch.setattr(calendar_module, "_find_cross_business_alternatives", AsyncMock(return_value=cross))
    monkeypatch.setattr(calendar_module, "_find_same_business_alternatives", AsyncMock(return_value=same))

    alternatives = await _find_alternatives(
        AsyncMock(),
        user_id=1,
        business_id=5,
        category="Berber",
        exclude_slot_id=99,
        requested_start=datetime(2026, 8, 1, 10, 0),
        online_only=False,
        gender=None,
        min_price=None,
        max_price=None,
    )

    assert [alt.appointment_slot_id for alt in alternatives] == [1, 2]


async def test_claim_slot_returns_true_when_row_updated() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=1)

    assert await _claim_slot(session, 1) is True


async def test_claim_slot_returns_false_when_no_row_updated() -> None:
    """Slot zaten başka biri tarafından kapılmışsa (yarış durumu kaybedildi)."""
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=0)

    assert await _claim_slot(session, 1) is False


async def test_book_appointment_raises_slot_not_found_error_when_slot_missing(monkeypatch) -> None:
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=None))

    with pytest.raises(SlotNotFoundError):
        await book_appointment(AsyncMock(), user_id=1, appointment_slot_id=999)


async def test_book_appointment_returns_alternatives_when_slot_already_booked(monkeypatch) -> None:
    now = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=(5, "Berber", now, 30, True)))
    monkeypatch.setattr(calendar_module, "_find_alternatives", AsyncMock(return_value=[_make_alternative()]))

    response = await book_appointment(AsyncMock(), user_id=1, appointment_slot_id=10)

    assert response.success is False
    assert response.booking_id is None
    assert len(response.alternatives) == 1


async def test_book_appointment_returns_alternatives_when_user_has_conflict(monkeypatch) -> None:
    now = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=(5, "Berber", now, 30, False)))
    monkeypatch.setattr(calendar_module, "_has_user_conflict", AsyncMock(return_value=True))
    monkeypatch.setattr(calendar_module, "_find_alternatives", AsyncMock(return_value=[]))

    response = await book_appointment(AsyncMock(), user_id=1, appointment_slot_id=10)

    assert response.success is False


async def test_book_appointment_returns_alternatives_when_claim_fails_due_to_race(monkeypatch) -> None:
    """Slot uygun görünüyordu ama _claim_slot arada başka bir isteğin
    kaptığını (rowcount=0) fark etti — bu durumda da alternatif dönülmeli."""
    now = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=(5, "Berber", now, 30, False)))
    monkeypatch.setattr(calendar_module, "_has_user_conflict", AsyncMock(return_value=False))
    monkeypatch.setattr(calendar_module, "_claim_slot", AsyncMock(return_value=False))
    monkeypatch.setattr(calendar_module, "_find_alternatives", AsyncMock(return_value=[]))

    response = await book_appointment(AsyncMock(), user_id=1, appointment_slot_id=10)

    assert response.success is False


async def test_book_appointment_succeeds_when_slot_free_and_no_conflict(monkeypatch) -> None:
    now = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=(5, "Berber", now, 30, False)))
    monkeypatch.setattr(calendar_module, "_has_user_conflict", AsyncMock(return_value=False))
    monkeypatch.setattr(calendar_module, "_claim_slot", AsyncMock(return_value=True))
    session = AsyncMock()
    session.add = MagicMock()  # gerçek AsyncSession.add() senkron, I/O yapmaz

    response = await book_appointment(session, user_id=1, appointment_slot_id=10)

    assert response.success is True
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


async def test_book_appointment_passes_filters_through_to_find_alternatives(monkeypatch) -> None:
    """online_only/gender/fiyat kısıtları, çağıran /recommend'den geldiyse
    alternatif aramasına da ulaşmalı (bkz. BookRequest docstring'i)."""
    now = datetime(2026, 8, 1, 10, 0)
    monkeypatch.setattr(calendar_module, "_fetch_slot", AsyncMock(return_value=(5, "Berber", now, 30, True)))
    captured: dict = {}

    async def fake_find_alternatives(session, user_id, business_id, category, exclude_slot_id, requested_start, online_only, gender, min_price, max_price):
        captured.update(
            online_only=online_only, gender=gender, min_price=min_price, max_price=max_price
        )
        return []

    monkeypatch.setattr(calendar_module, "_find_alternatives", fake_find_alternatives)

    await book_appointment(
        AsyncMock(), user_id=1, appointment_slot_id=10,
        online_only=True, gender="unisex", min_price=100, max_price=500,
    )

    assert captured == {"online_only": True, "gender": "unisex", "min_price": 100, "max_price": 500}

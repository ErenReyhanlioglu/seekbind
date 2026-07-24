"""Çalışma saatleri (jitter + hafta sonu olasılığı) ve randevu slotu üretimi."""

import random
from datetime import date, datetime, timedelta

from scripts.constants import (
    SATURDAY_OPEN_PROBABILITY,
    SUNDAY_OPEN_PROBABILITY,
    WORKING_HOURS_JITTER_OPTIONS_MIN,
    WORKING_HOURS_TEMPLATE,
)
from scripts.schemas import WorkingHours, WorkingHoursDay

SLOT_GENERATION_DAYS_AHEAD: int = 7
BOOKED_SLOT_PROBABILITY: float = 0.3

TIME_FORMAT: str = "%H:%M"
SLOT_DATETIME_FORMAT: str = "%Y-%m-%d %H:%M"
MAX_MINUTES_IN_DAY: int = 23 * 60 + 59


def _shift_time_within_day(time_str: str, jitter_min: int) -> str:
    """Saate jitter uygular, gece yarısını taşırmadan aynı gün içinde sıkıştırır (clamp)."""
    base_minutes = int(time_str[:2]) * 60 + int(time_str[3:5])
    shifted = max(0, min(MAX_MINUTES_IN_DAY, base_minutes + jitter_min))
    return f"{shifted // 60:02d}:{shifted % 60:02d}"


def _apply_jitter(
    template_hours: tuple[str, str] | None,
    open_probability: float | None,
    open_jitter_min: int,
    close_jitter_min: int,
) -> WorkingHoursDay:
    """Bir günün taban saatine jitter uygular, olasılığa göre kapalı sayabilir."""
    if template_hours is None:
        return WorkingHoursDay(open=None, close=None)
    if open_probability is not None and random.random() > open_probability:
        return WorkingHoursDay(open=None, close=None)

    open_str, close_str = template_hours
    new_open = _shift_time_within_day(open_str, open_jitter_min)
    new_close = _shift_time_within_day(close_str, close_jitter_min)
    if new_open >= new_close:
        # Clamp sonrası hala gecersizse (asiri kisa pencere), jitter'siz taban saate don
        return WorkingHoursDay(open=open_str, close=close_str)
    return WorkingHoursDay(open=new_open, close=new_close)


def _pick_jitter_minutes() -> int:
    """WORKING_HOURS_JITTER_OPTIONS_MIN'den işaretli (+/-) bir sapma seçer."""
    return random.choice(WORKING_HOURS_JITTER_OPTIONS_MIN) * random.choice((-1, 1))


def build_working_hours(type_normalized: str) -> WorkingHours:
    """İşletme için jitter uygulanmış, olasılığa göre hafta sonu ayarlı çalışma saatleri üretir."""
    template = WORKING_HOURS_TEMPLATE[type_normalized]
    open_jitter = _pick_jitter_minutes()
    close_jitter = _pick_jitter_minutes()

    weekday = _apply_jitter(template["weekday"], None, open_jitter, close_jitter)
    saturday = _apply_jitter(
        template["saturday"], SATURDAY_OPEN_PROBABILITY.get(type_normalized), open_jitter, close_jitter
    )
    sunday = _apply_jitter(
        template["sunday"], SUNDAY_OPEN_PROBABILITY.get(type_normalized), open_jitter, close_jitter
    )
    return WorkingHours(weekday=weekday, saturday=saturday, sunday=sunday)


def _day_hours(working_hours: WorkingHours, day: date) -> WorkingHoursDay:
    """Haftanın gününe (0=Pazartesi...6=Pazar) göre ilgili çalışma saatini döner."""
    weekday_index = day.weekday()
    if weekday_index == 5:
        return working_hours.saturday
    if weekday_index == 6:
        return working_hours.sunday
    return working_hours.weekday


def generate_slots(working_hours: WorkingHours, duration_min: int) -> tuple[list[str], list[str]]:
    """Önümüzdeki SLOT_GENERATION_DAYS_AHEAD gün için müsait/dolu slotları üretir."""
    available: list[str] = []
    booked: list[str] = []
    start_date = datetime.now().date() + timedelta(days=1)

    for offset in range(SLOT_GENERATION_DAYS_AHEAD):
        current_day = start_date + timedelta(days=offset)
        hours = _day_hours(working_hours, current_day)
        if hours.open is None or hours.close is None:
            continue

        slot_start = datetime.combine(current_day, datetime.strptime(hours.open, TIME_FORMAT).time())
        day_close = datetime.combine(current_day, datetime.strptime(hours.close, TIME_FORMAT).time())

        while slot_start + timedelta(minutes=duration_min) <= day_close:
            slot_str = slot_start.strftime(SLOT_DATETIME_FORMAT)
            target = booked if random.random() < BOOKED_SLOT_PROBABILITY else available
            target.append(slot_str)
            slot_start += timedelta(minutes=duration_min)

    return available, booked

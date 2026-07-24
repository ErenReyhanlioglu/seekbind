"""Sentetik veri üretimi için kategori bazlı sabit sözlükler."""

from scripts.constants.attributes import (
    DEFAULT_GENDER_PREFERENCE_WEIGHTS,
    GENDER_PREFERENCE_WEIGHTS,
    ONLINE_AVAILABLE,
)
from scripts.constants.business_types import QUERY_TERM_TO_TYPE
from scripts.constants.pricing import APPOINTMENT_DURATIONS_MIN, PRICE_RANGES_TL
from scripts.constants.service_taxonomy import SERVICE_TAXONOMY
from scripts.constants.working_hours import (
    SATURDAY_OPEN_PROBABILITY,
    SUNDAY_OPEN_PROBABILITY,
    WORKING_HOURS_JITTER_OPTIONS_MIN,
    WORKING_HOURS_TEMPLATE,
)

__all__ = [
    "APPOINTMENT_DURATIONS_MIN",
    "DEFAULT_GENDER_PREFERENCE_WEIGHTS",
    "GENDER_PREFERENCE_WEIGHTS",
    "ONLINE_AVAILABLE",
    "PRICE_RANGES_TL",
    "QUERY_TERM_TO_TYPE",
    "SATURDAY_OPEN_PROBABILITY",
    "SERVICE_TAXONOMY",
    "SUNDAY_OPEN_PROBABILITY",
    "WORKING_HOURS_JITTER_OPTIONS_MIN",
    "WORKING_HOURS_TEMPLATE",
]

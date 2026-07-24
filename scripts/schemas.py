"""data/processed/businesses.jsonl için ortak Pydantic şeması.

generate_synthetic.py bu şemayı doldurur (rich_description hariç),
enrich_with_llm.py aynı şemayı okuyup sadece rich_description'ı ekler.
"""

from pydantic import BaseModel


class PriceRange(BaseModel):
    """TL cinsinden fiyat aralığı."""

    min: int
    max: int


class WorkingHoursDay(BaseModel):
    """Bir günün açılış/kapanış saati, kapalıysa ikisi de None."""

    open: str | None
    close: str | None


class WorkingHours(BaseModel):
    """Haftalık çalışma saatleri (haftaiçi/cumartesi/pazar)."""

    weekday: WorkingHoursDay
    saturday: WorkingHoursDay
    sunday: WorkingHoursDay


class ProcessedBusinessRecord(BaseModel):
    """data/processed/businesses.jsonl'a yazılan tekil işletme kaydı."""

    place_id: str
    title: str
    type_normalized: str
    rating: float | None
    reviews: int
    address: str | None
    phone: str | None
    gps_coordinates: dict[str, float] | None
    services: list[str]
    price_range_tl: PriceRange
    appointment_duration_min: int
    online_available: bool
    gender: str
    working_hours: WorkingHours
    available_slots: list[str]
    booked_slots: list[str]
    rich_description: str | None = None

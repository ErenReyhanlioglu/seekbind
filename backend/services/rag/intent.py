"""Serbest metin sorguyu yapılandırılmış filtrelere ayrıştırma (intent parsing).

ADR-0011'e göre `response_format=json_object` kullanır — gerçek Tool Calling
API'si değil. Tek tek geçersiz enum-benzeri alanlar (gender/category/
day_of_week/time_of_day) hata fırlatmaz, sessizce None'a düşürülür (bkz.
`ParsedIntent._coerce_invalid_enums`); tam fallback'i (çağıranın ham sorgu +
boş filtreye düşmesi, bkz. `backend.services.rag.service`) sadece
`semantic_query` eksikliği/boşluğu ya da LLM/JSON hatası tetikler.
"""

import json
import logging
from datetime import date, timedelta
from typing import Literal, get_args

from pydantic import BaseModel, Field, ValidationError, model_validator

from backend.services.llm import ChatMessage, LLMProvider, LLMServiceError
from backend.services.rag.prompts import SEARCH_INTENT_PROMPT_PATH, SYSTEM_PROMPT_PATH, load_prompt
from backend.services.search import DateAvailabilityFilter, SearchFilters, normalize_turkish_text
from backend.services.search.availability import TimeOfDay
from scripts.constants.business_types import QUERY_TERM_TO_TYPE

logger = logging.getLogger(__name__)

# scripts/'tan import: 27 kategori değerinin ikinci bir elle-tutulan kopyasını
# önlemek için tek kaynak burası (scripts/constants/business_types.py) — bu
# repoda backend/'in scripts/'tan import ettiği ilk yer, ama saf veri/sıfır
# I/O olduğu için güvenli.
VALID_CATEGORIES: frozenset[str] = frozenset(QUERY_TERM_TO_TYPE.values())

DayOfWeek = Literal["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
_DAY_NAMES: tuple[str, ...] = get_args(DayOfWeek)
_WEEKDAY_INDEX: dict[str, int] = {name: i for i, name in enumerate(_DAY_NAMES)}

_JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}
_INTENT_TEMPERATURE: float = 0.0  # yapılandırılmış çıkarım, yaratıcılık istemiyoruz


class IntentParsingError(Exception):
    """LLM çağrısı, JSON parse ya da zorunlu `semantic_query` eksik/boş olduğunda."""


class ParsedIntent(BaseModel):
    """`search_intent.txt`'in ürettiği JSON'un tip güvenli karşılığı.

    Tek tek geçersiz enum-benzeri alanlar hata fırlatmaz, sessizce None'a
    düşürülür — tam fallback'i sadece `semantic_query` eksikliği/boşluğu
    tetikler (bkz. `_coerce_invalid_enums` ve `Field(min_length=1)`).
    """

    model_config = {"extra": "ignore"}

    semantic_query: str = Field(min_length=1)
    min_price: int | None = None
    max_price: int | None = None
    gender: Literal["female", "male", "unisex"] | None = None
    category: str | None = None
    online_only: bool = False
    weekend_open_only: bool = False
    day_of_week: DayOfWeek | None = None
    time_of_day: TimeOfDay | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_invalid_enums(cls, data: object) -> object:
        """Bilinmeyen/geçersiz gender, category, day_of_week, time_of_day
        değerlerini hata fırlatmadan None'a düşürür (log ile)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)

        gender = data.get("gender")
        if gender not in ("female", "male", "unisex", None):
            logger.warning("Geçersiz gender değeri düşürüldü: %r", gender)
            data["gender"] = None

        category = data.get("category")
        if category is not None and category not in VALID_CATEGORIES:
            logger.warning("Geçersiz category değeri düşürüldü: %r", category)
            data["category"] = None

        day_of_week = data.get("day_of_week")
        if day_of_week is not None:
            normalized = normalize_turkish_text(str(day_of_week)).strip()
            if normalized not in _DAY_NAMES:
                logger.warning("Geçersiz day_of_week değeri düşürüldü: %r", day_of_week)
                normalized = None
            data["day_of_week"] = normalized

        time_of_day = data.get("time_of_day")
        if time_of_day not in ("morning", "afternoon", "evening", None):
            logger.warning("Geçersiz time_of_day değeri düşürüldü: %r", time_of_day)
            data["time_of_day"] = None

        return data


def resolve_day_of_week(day_of_week: DayOfWeek, today: date) -> date:
    """Gün adını, bugünden itibaren en yakın (bugün dahil) tekrarına çevirir.

    Saf ve deterministik — LLM'den gerçek bir takvim tarihi istemiyoruz
    (bkz. `search_intent.txt`), bu hesaplamayı LLM'e hiç güvenmeden burada
    yapıyoruz. `_DAY_NAMES`'in sırası Python'un `date.weekday()`'iyle
    (Pazartesi=0 ... Pazar=6) birebir eşleşecek şekilde tanımlandı.
    """
    target_index = _WEEKDAY_INDEX[day_of_week]
    days_ahead = (target_index - today.weekday()) % 7
    return today + timedelta(days=days_ahead)


def build_search_filters(intent: ParsedIntent) -> SearchFilters:
    """ParsedIntent'ten SearchFilters üretir — düz alan eşlemesi."""
    return SearchFilters(
        min_price=intent.min_price,
        max_price=intent.max_price,
        gender=intent.gender,
        category=intent.category,
        online_only=intent.online_only,
        weekend_open_only=intent.weekend_open_only,
    )


def build_availability_filter(intent: ParsedIntent, today: date) -> DateAvailabilityFilter | None:
    """`day_of_week` yoksa None döner — `time_of_day` tek başına yeterli
    değil, şemada "herhangi bir gün, sabahları" diye bir temsil yok."""
    if intent.day_of_week is None:
        return None
    return DateAvailabilityFilter(
        date=resolve_day_of_week(intent.day_of_week, today),
        time_of_day=intent.time_of_day,
    )


async def parse_intent(llm_provider: LLMProvider, raw_query: str, today: date) -> ParsedIntent:
    """Serbest metin sorguyu LLM ile yapılandırılmış `ParsedIntent`'e ayrıştırır.

    Başarısız olursa (LLM hatası, bozuk/beklenmedik şekilli JSON,
    `semantic_query` eksik/boş) `IntentParsingError` fırlatır — çağıran
    (`backend.services.rag.service.get_recommendation`) bunu yakalayıp ham
    sorgu + boş filtreyle devam eder.
    """
    system_content = load_prompt(SYSTEM_PROMPT_PATH)
    intent_instructions = load_prompt(SEARCH_INTENT_PROMPT_PATH).format(
        today_weekday=_DAY_NAMES[today.weekday()],
        categories=", ".join(sorted(VALID_CATEGORIES)),
    )
    messages = [
        ChatMessage(role="system", content=system_content),
        ChatMessage(role="user", content=f'{intent_instructions}\n\nSorgu: "{raw_query}"'),
    ]

    try:
        response = await llm_provider.complete(
            messages, temperature=_INTENT_TEMPERATURE, response_format=_JSON_RESPONSE_FORMAT
        )
    except LLMServiceError as e:
        raise IntentParsingError("Intent parsing LLM çağrısı başarısız") from e

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as e:
        raise IntentParsingError("Intent parsing yanıtı geçerli JSON değil") from e
    if not isinstance(payload, dict):
        raise IntentParsingError("Intent parsing yanıtı bir JSON nesnesi değil")

    try:
        return ParsedIntent(**payload)
    except ValidationError as e:
        raise IntentParsingError("Intent parsing yanıtı beklenen şemaya uymuyor") from e

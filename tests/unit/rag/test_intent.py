"""backend/services/rag/intent.py için birim testler."""

from datetime import date
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.llm import ChatMessage, LLMResponse, LLMServiceError
from backend.services.rag.intent import (
    IntentParsingError,
    ParsedIntent,
    build_availability_filter,
    build_search_filters,
    parse_intent,
    resolve_day_of_week,
)


class _FakeLLMProvider:
    """LLMProvider Protocol'üne uyan, elle yazılmış test double'ı."""

    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        content: str = "",
        error: Exception | None = None,
        from_cache: bool = False,
    ) -> None:
        self._content = content
        self._error = error
        self._from_cache = from_cache
        self.last_response_format: dict[str, str] | None = None
        self.last_langfuse_name: str | None = None
        self.last_langfuse_metadata: dict[str, object] | None = None

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        langfuse_name: str | None = None,
        langfuse_metadata: dict[str, object] | None = None,
    ) -> LLMResponse:
        self.last_response_format = response_format
        self.last_langfuse_name = langfuse_name
        self.last_langfuse_metadata = langfuse_metadata
        if self._error is not None:
            raise self._error
        return LLMResponse(
            content=self._content,
            model="fake-model",
            provider="fake",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            finish_reason="stop",
            from_cache=self._from_cache,
        )

    async def close(self) -> None:
        pass


# 2026-07-28 gerçekten bir salı — testlerde de bu referans kullanılıyor.
_TUESDAY = date(2026, 7, 28)


def test_resolve_day_of_week_returns_today_when_today_matches() -> None:
    assert resolve_day_of_week("salı", _TUESDAY) == _TUESDAY


def test_resolve_day_of_week_returns_next_occurrence_when_day_already_passed_this_week() -> (
    None
):
    # pazartesi salıdan önce gelir ama bu haftaki pazartesi geçti -> +6 gün
    assert resolve_day_of_week("pazartesi", _TUESDAY) == date(2026, 8, 3)


def test_resolve_day_of_week_returns_upcoming_day_within_same_week() -> None:
    assert resolve_day_of_week("cuma", _TUESDAY) == date(2026, 7, 31)


def test_resolve_day_of_week_wraps_across_year_boundary() -> None:
    new_years_eve = date(2026, 12, 30)  # çarşamba
    assert resolve_day_of_week("cuma", new_years_eve) == date(2027, 1, 1)


async def test_parse_intent_returns_parsed_intent_on_valid_json_response() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "category": "Diş Kliniği", "min_price": null, '
        '"max_price": 500, "gender": "unisex", "online_only": false, "weekend_open_only": false, '
        '"day_of_week": "salı", "time_of_day": "morning"}'
    )

    intent, _ = await parse_intent(provider, "salı sabahı ucuz dişçi", _TUESDAY)

    assert intent.semantic_query == "dişçi"
    assert intent.category == "Diş Kliniği"
    assert intent.max_price == 500
    assert provider.last_langfuse_name == "intent_parsing"
    assert provider.last_langfuse_metadata == {"raw_query": "salı sabahı ucuz dişçi"}
    assert intent.day_of_week == "salı"
    assert intent.time_of_day == "morning"
    assert provider.last_response_format == {"type": "json_object"}


async def test_parse_intent_returns_cache_hit_flag_from_llm_response() -> None:
    """`parse_intent()`'in ikinci dönüş elemanı, `LLMResponse.from_cache`'i
    olduğu gibi taşımalı (bkz. `CachedLLMProvider`)."""
    cached_provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi"}', from_cache=True
    )
    fresh_provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi"}', from_cache=False
    )

    _, cached_hit = await parse_intent(cached_provider, "dişçi", _TUESDAY)
    _, fresh_hit = await parse_intent(fresh_provider, "dişçi", _TUESDAY)

    assert cached_hit is True
    assert fresh_hit is False


async def test_parse_intent_raises_intent_parsing_error_on_malformed_json() -> None:
    provider = _FakeLLMProvider(content="bu JSON değil")

    with pytest.raises(IntentParsingError):
        await parse_intent(provider, "dişçi", _TUESDAY)


async def test_parse_intent_raises_intent_parsing_error_when_semantic_query_missing() -> (
    None
):
    provider = _FakeLLMProvider(content='{"category": "Diş Kliniği"}')

    with pytest.raises(IntentParsingError):
        await parse_intent(provider, "dişçi", _TUESDAY)


async def test_parse_intent_raises_intent_parsing_error_when_llm_call_fails() -> None:
    provider = _FakeLLMProvider(error=LLMServiceError("bağlantı hatası"))

    with pytest.raises(IntentParsingError):
        await parse_intent(provider, "dişçi", _TUESDAY)


async def test_parse_intent_raises_intent_parsing_error_when_json_is_not_an_object() -> (
    None
):
    """LLM geçerli JSON döndürebilir ama obje olmayabilir (örn. bir dizi) —
    json.loads() burada hata fırlatmaz, ayrıca kontrol etmemiz gerekiyor."""
    provider = _FakeLLMProvider(content='["dişçi", "kuaför"]')

    with pytest.raises(IntentParsingError):
        await parse_intent(provider, "dişçi", _TUESDAY)


def test_parsed_intent_model_validate_raises_validation_error_for_non_dict_input() -> (
    None
):
    """`parse_intent()` dict-olmayan JSON'u zaten kendi kontrolüyle eliyor
    (bkz. yukarıdaki test), ama `ParsedIntent`'in kendi `_coerce_invalid_enums`
    validator'ı da bağımsız olarak savunmacı: dict olmayan bir girdi
    (örn. doğrudan `model_validate` ile) hiçbir alanı işlemeye çalışmadan
    veriyi olduğu gibi bırakır, pydantic'in kendi "dict bekleniyor" hatası
    fırlatılır."""
    with pytest.raises(ValidationError):
        ParsedIntent.model_validate(["dişçi", "kuaför"])


async def test_parse_intent_drops_invalid_time_of_day_but_keeps_other_fields() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "time_of_day": "gece_yarisi", "category": "Diş Kliniği"}'
    )

    intent, _ = await parse_intent(provider, "dişçi", _TUESDAY)

    assert intent.time_of_day is None
    assert intent.category == "Diş Kliniği"


async def test_parse_intent_drops_invalid_price_preference_but_keeps_other_fields() -> (
    None
):
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "price_preference": "biraz_ucuz", "category": "Diş Kliniği"}'
    )

    intent, _ = await parse_intent(provider, "dişçi", _TUESDAY)

    assert intent.price_preference is None
    assert intent.category == "Diş Kliniği"


async def test_parse_intent_extracts_valid_price_preference() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "ucuz dişçi", "price_preference": "cheap"}'
    )

    intent, _ = await parse_intent(provider, "ucuz dişçi", _TUESDAY)

    assert intent.price_preference == "cheap"


async def test_parse_intent_drops_invalid_rating_preference_but_keeps_other_fields() -> (
    None
):
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "rating_preference": "en_iyi", "category": "Diş Kliniği"}'
    )

    intent, _ = await parse_intent(provider, "dişçi", _TUESDAY)

    assert intent.rating_preference is None
    assert intent.category == "Diş Kliniği"


async def test_parse_intent_extracts_valid_rating_preference() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "en kötü dişçi", "rating_preference": "low"}'
    )

    intent, _ = await parse_intent(provider, "en kötü dişçi", _TUESDAY)

    assert intent.rating_preference == "low"


async def test_parse_intent_drops_invalid_category_but_keeps_other_fields() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "category": "Uydurma Kategori", "min_price": 100}'
    )

    intent, _ = await parse_intent(provider, "dişçi", _TUESDAY)

    assert intent.category is None
    assert intent.min_price == 100


async def test_parse_intent_drops_non_string_category_instead_of_raising() -> None:
    """Gerçek bir ablasyon çalıştırmasında bulunan regresyon: LLM (çoklu
    kategori istenen bir sorguda, örn. "hem dişçi hem kuaför") category'yi
    tek bir string yerine bir liste döndürebilir — `VALID_CATEGORIES`
    frozenset üyelik testi (`in`) hash gerektirdiği için isinstance kontrolü
    olmadan TypeError fırlatırdı (bkz. rag/intent.py _coerce_invalid_enums)."""
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi ve kuaför", "category": ["Diş Kliniği", "Kuaför"]}'
    )

    intent, _ = await parse_intent(provider, "hem dişçi hem kuaför istiyorum", _TUESDAY)

    assert intent.category is None


async def test_parse_intent_drops_invalid_gender_but_keeps_other_fields() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "kuaför", "gender": "erkek", "max_price": 300}'
    )

    intent, _ = await parse_intent(provider, "kuaför", _TUESDAY)

    assert intent.gender is None
    assert intent.max_price == 300


async def test_parse_intent_normalizes_capitalized_day_of_week() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "day_of_week": "Salı"}'
    )

    intent, _ = await parse_intent(provider, "salı dişçi", _TUESDAY)

    assert intent.day_of_week == "salı"


async def test_parse_intent_drops_unrecognized_day_of_week() -> None:
    provider = _FakeLLMProvider(
        content='{"semantic_query": "dişçi", "day_of_week": "yakında"}'
    )

    intent, _ = await parse_intent(provider, "dişçi", _TUESDAY)

    assert intent.day_of_week is None


async def test_build_search_filters_maps_all_fields() -> None:
    intent = ParsedIntent(
        semantic_query="dişçi",
        min_price=100,
        max_price=500,
        gender="unisex",
        category="Diş Kliniği",
        online_only=True,
        weekend_open_only=True,
    )
    # min/max_price zaten dolu olduğu için resolve_price_threshold hiç
    # çağrılmaz, session'a hiç dokunulmaz — gerçek bir session vermeye gerek yok
    unused_session = cast(AsyncSession, object())

    filters = await build_search_filters(intent, unused_session)

    assert filters.min_price == 100
    assert filters.max_price == 500
    assert filters.gender == "unisex"
    assert filters.category == "Diş Kliniği"
    assert filters.online_only is True
    assert filters.weekend_open_only is True


async def test_build_search_filters_resolves_price_from_preference_when_no_explicit_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """min_price/max_price yoksa ama price_preference varsa,
    resolve_price_threshold() çağrılıp sonucu kullanılmalı."""
    intent = ParsedIntent(
        semantic_query="ucuz dişçi", category="Diş Kliniği", price_preference="cheap"
    )

    async def fake_resolve_price_threshold(
        session, category, preference
    ):  # noqa: ANN001
        assert category == "Diş Kliniği"
        assert preference == "cheap"
        return None, 900

    monkeypatch.setattr(
        "backend.services.rag.intent.resolve_price_threshold",
        fake_resolve_price_threshold,
    )

    filters = await build_search_filters(intent, cast(AsyncSession, object()))

    assert filters.min_price is None
    assert filters.max_price == 900


async def test_build_search_filters_does_not_resolve_price_when_explicit_number_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """min_price/max_price zaten doluysa, price_preference olsa bile
    resolve_price_threshold() hiç çağrılmamalı (LLM'in somut sayısı kazanır)."""
    intent = ParsedIntent(
        semantic_query="300 TL'den ucuz dişçi",
        category="Diş Kliniği",
        max_price=300,
        price_preference="cheap",
    )
    called = False

    async def fake_resolve_price_threshold(
        session, category, preference
    ):  # noqa: ANN001
        nonlocal called
        called = True
        return None, 900

    monkeypatch.setattr(
        "backend.services.rag.intent.resolve_price_threshold",
        fake_resolve_price_threshold,
    )

    filters = await build_search_filters(intent, cast(AsyncSession, object()))

    assert called is False
    assert filters.max_price == 300


def test_build_availability_filter_returns_none_when_day_of_week_absent() -> None:
    intent = ParsedIntent(semantic_query="dişçi", time_of_day="morning")

    assert build_availability_filter(intent, _TUESDAY) is None


def test_build_availability_filter_resolves_date_when_day_of_week_present() -> None:
    intent = ParsedIntent(
        semantic_query="dişçi", day_of_week="cuma", time_of_day="morning"
    )

    availability = build_availability_filter(intent, _TUESDAY)

    assert availability is not None
    assert availability.date == date(2026, 7, 31)
    assert availability.time_of_day == "morning"

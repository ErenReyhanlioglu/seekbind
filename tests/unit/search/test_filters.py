"""backend/services/search/filters.py için birim testler."""

from typing import cast

from qdrant_client.models import FieldCondition, Filter, GeoRadius, MatchValue, Range

from backend.services.search.filters import NearFilter, SearchFilters, translate_filters_to_qdrant


def _require_conditions(qdrant_filter: Filter | None) -> list[FieldCondition]:
    """Testte None-check tekrarını önler; translate_filters_to_qdrant her zaman
    sadece FieldCondition ürettiği için (bkz. filters.py) dönüş tipi buna daraltılır.

    Her elemanı isinstance ile gerçekten doğruluyoruz (runtime garantisi), sonra
    cast() ile type checker'a bunu bildiriyoruz — Pyright'ın union daraltmasında
    burada tutarsız davrandığı görüldü (list[Never] çıkarımı), cast daha güvenilir.
    """
    assert qdrant_filter is not None
    assert qdrant_filter.must is not None
    must = qdrant_filter.must if isinstance(qdrant_filter.must, list) else [qdrant_filter.must]
    for condition in must:
        assert isinstance(condition, FieldCondition)
    return cast(list[FieldCondition], must)


def _condition_keys(qdrant_filter: Filter | None) -> list[str]:
    return [condition.key for condition in _require_conditions(qdrant_filter)]


def _require_range(condition: FieldCondition) -> Range:
    """FieldCondition.range Optional olduğu için erişimden önce daraltır."""
    assert condition.range is not None
    assert isinstance(condition.range, Range)
    return condition.range


def _require_match_value(condition: FieldCondition) -> object:
    """FieldCondition.match birden fazla alt tip olabilir, sadece MatchValue'nun .value'su var."""
    assert condition.match is not None
    assert isinstance(condition.match, MatchValue)
    return condition.match.value


def _require_geo_radius(condition: FieldCondition) -> GeoRadius:
    """FieldCondition.geo_radius Optional olduğu için erişimden önce daraltır."""
    assert condition.geo_radius is not None
    return condition.geo_radius


def test_translate_filters_returns_none_for_empty_filters() -> None:
    assert translate_filters_to_qdrant(SearchFilters()) is None


def test_translate_filters_creates_price_range_conditions() -> None:
    result = translate_filters_to_qdrant(SearchFilters(min_price=100, max_price=500))

    conditions = {c.key: c for c in _require_conditions(result)}
    assert _require_range(conditions["price_min"]).lte == 500
    assert _require_range(conditions["price_max"]).gte == 100


def test_translate_filters_creates_gender_condition() -> None:
    result = translate_filters_to_qdrant(SearchFilters(gender="female"))

    conditions = _require_conditions(result)
    assert [c.key for c in conditions] == ["gender"]
    assert _require_match_value(conditions[0]) == "female"


def test_translate_filters_creates_category_condition() -> None:
    result = translate_filters_to_qdrant(SearchFilters(category="Diş Kliniği"))

    assert _condition_keys(result) == ["type_normalized"]


def test_translate_filters_only_adds_online_condition_when_true() -> None:
    assert translate_filters_to_qdrant(SearchFilters(online_only=False)) is None

    result = translate_filters_to_qdrant(SearchFilters(online_only=True))
    assert _condition_keys(result) == ["online_available"]


def test_translate_filters_only_adds_weekend_condition_when_true() -> None:
    assert translate_filters_to_qdrant(SearchFilters(weekend_open_only=False)) is None

    result = translate_filters_to_qdrant(SearchFilters(weekend_open_only=True))
    assert _condition_keys(result) == ["open_weekend"]


def test_translate_filters_converts_near_filter_radius_to_meters() -> None:
    near = NearFilter(latitude=40.77, longitude=29.92, radius_km=2.5)
    result = translate_filters_to_qdrant(SearchFilters(near=near))

    condition = _require_conditions(result)[0]
    geo_radius = _require_geo_radius(condition)
    assert condition.key == "location"
    assert geo_radius.radius == 2500
    assert geo_radius.center.lat == 40.77
    assert geo_radius.center.lon == 29.92


def test_translate_filters_combines_multiple_conditions() -> None:
    result = translate_filters_to_qdrant(SearchFilters(gender="unisex", online_only=True, max_price=300))

    assert set(_condition_keys(result)) == {"gender", "online_available", "price_min"}

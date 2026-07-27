"""SearchFilters — arama isteğine uygulanacak kesin (hard) filtreler ve
bunların Qdrant Filter/FieldCondition nesnelerine çevrilmesi."""

from typing import Literal

from pydantic import BaseModel
from qdrant_client.models import Condition, FieldCondition, Filter, GeoPoint, GeoRadius, MatchValue, Range

METERS_PER_KM: int = 1000


class NearFilter(BaseModel):
    """Kullanıcının konumuna göre mesafe filtresi.

    Kullanıcının koordinatını nereden aldığı (login, LLM'in 'yakınımda'
    sorgusunu ayrıştırması vb.) search-service'i ilgilendirmez — sadece
    hazır bir (lat, lon, yarıçap) üçlüsü kabul eder.
    """

    latitude: float
    longitude: float
    radius_km: float


class SearchFilters(BaseModel):
    """Aramaya uygulanacak kesin (hard) filtreler — Qdrant payload filtering ile uygulanır."""

    min_price: int | None = None
    max_price: int | None = None
    gender: Literal["female", "male", "unisex"] | None = None
    category: str | None = None
    online_only: bool = False
    weekend_open_only: bool = False
    near: NearFilter | None = None


def translate_filters_to_qdrant(filters: SearchFilters) -> Filter | None:
    """SearchFilters'ı Qdrant'ın Filter/FieldCondition nesnelerine çevirir.

    Fiyat, min_price/max_price ile business.price_min/price_max arasında
    aralık örtüşmesi (overlap) olarak modellenir — kullanıcının bütçesiyle
    işletmenin fiyat aralığının kesişip kesişmediğine bakılır, tek bir
    noktaya eşitlik değil.
    """
    conditions: list[Condition] = []

    if filters.max_price is not None:
        conditions.append(FieldCondition(key="price_min", range=Range(lte=filters.max_price)))
    if filters.min_price is not None:
        conditions.append(FieldCondition(key="price_max", range=Range(gte=filters.min_price)))
    if filters.gender is not None:
        conditions.append(FieldCondition(key="gender", match=MatchValue(value=filters.gender)))
    if filters.category is not None:
        conditions.append(FieldCondition(key="type_normalized", match=MatchValue(value=filters.category)))
    if filters.online_only:
        conditions.append(FieldCondition(key="online_available", match=MatchValue(value=True)))
    if filters.weekend_open_only:
        conditions.append(FieldCondition(key="open_weekend", match=MatchValue(value=True)))
    if filters.near is not None:
        conditions.append(
            FieldCondition(
                key="location",
                geo_radius=GeoRadius(
                    center=GeoPoint(lon=filters.near.longitude, lat=filters.near.latitude),
                    radius=filters.near.radius_km * METERS_PER_KM,
                ),
            )
        )

    if not conditions:
        return None
    return Filter(must=conditions)

"""Yüklem tanımları: gender/day/price/service_keyword -> işletme id kümesi.

`combination_search.py`'nin çok-yüklemli aramasına girdi sağlar. "online"
yüklemi özel olarak eleniyor değil — ADR-0027'deki bulgu (27 kategorinin
tamamında ya %0 ya %100, hep dejenere) bir önceki çalıştırmanın sonucuydu;
veri değişirse tekrar anlamlı çıkabilir, `combination_search.py`'deki
simetrik MIN_COUNT kontrolü her çalıştırmada doğru elemeyi otomatik yapar,
burada sabit bir özel durum eklenmiyor.
"""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from backend.services.rag.pricing import resolve_price_threshold
from scripts.ragas_testset.term_distinctiveness import TermCandidate


class Predicate(BaseModel):
    """Tek bir yüklem değeri: hangi tip, hangi değer, hangi işletmeler eşleşiyor."""

    type_name: str
    value_name: str
    matched_ids: frozenset[int]


def _gender_predicates(businesses: list[Business]) -> list[Predicate]:
    return [
        Predicate(
            type_name="gender",
            value_name=value,
            matched_ids=frozenset(b.id for b in businesses if b.gender == value),
        )
        for value in ("female", "male")
    ]


def _online_predicates(businesses: list[Business]) -> list[Predicate]:
    return [
        Predicate(
            type_name="online",
            value_name="online",
            matched_ids=frozenset(b.id for b in businesses if b.online_available),
        )
    ]


def _day_predicates(businesses: list[Business]) -> list[Predicate]:
    """Hafta içi/Cumartesi/Pazar + (sadece gerçekten yeni bilgi katıyorsa) hafta sonu birleşimi.

    `weekend_open`, cumartesi ya da pazarla birebir aynı kümeyi
    üretiyorsa (o kategoride pazar hiç açık değilse örneğin) eklenmiyor
    — collinear yüklemler aynı soruyu iki kez üretir (bkz. ADR-0027,
    Fizyoterapist'te weekend==saturday bulgusu). Veri modelinde
    pazartesi-cuma tek bir "weekday" kovasında toplu tutuluyor (bkz.
    `scripts/synthetic/schedule.py`), `day_of_week:pazartesi` ile
    `day_of_week:cuma` şema açısından aynı saatlere bakıyor.
    """
    weekday_ids = frozenset(
        b.id
        for b in businesses
        if b.working_hours.get("weekday", {}).get("open") is not None
    )
    saturday_ids = frozenset(
        b.id
        for b in businesses
        if b.working_hours.get("saturday", {}).get("open") is not None
    )
    sunday_ids = frozenset(
        b.id
        for b in businesses
        if b.working_hours.get("sunday", {}).get("open") is not None
    )
    weekend_ids = saturday_ids | sunday_ids

    predicates = [
        Predicate(type_name="day", value_name="weekday", matched_ids=weekday_ids),
        Predicate(type_name="day", value_name="saturday", matched_ids=saturday_ids),
        Predicate(type_name="day", value_name="sunday", matched_ids=sunday_ids),
    ]
    if weekend_ids != saturday_ids and weekend_ids != sunday_ids:
        predicates.append(
            Predicate(
                type_name="day", value_name="weekend_open", matched_ids=weekend_ids
            )
        )
    return predicates


async def _price_predicates(
    session: AsyncSession, category: str, businesses: list[Business]
) -> list[Predicate]:
    predicates: list[Predicate] = []
    for preference in ("cheap", "expensive"):
        min_price, max_price = await resolve_price_threshold(
            session, category, preference
        )
        matched_ids = frozenset(
            b.id
            for b in businesses
            if (max_price is None or b.price_min <= max_price)
            and (min_price is None or b.price_max >= min_price)
        )
        predicates.append(
            Predicate(type_name="price", value_name=preference, matched_ids=matched_ids)
        )
    return predicates


def _service_predicates(term_candidates: list[TermCandidate]) -> list[Predicate]:
    return [
        Predicate(
            type_name="service",
            value_name=candidate.lemma,
            matched_ids=candidate.matched_ids,
        )
        for candidate in term_candidates
    ]


async def build_predicate_groups(
    session: AsyncSession,
    category: str,
    businesses: list[Business],
    term_candidates: list[TermCandidate],
) -> list[list[Predicate]]:
    """Bir kategori için tüm yüklem tiplerini gruplu döner (aynı tipten iki değer aynı komboda olamaz)."""
    groups = [
        _gender_predicates(businesses),
        _online_predicates(businesses),
        _day_predicates(businesses),
        await _price_predicates(session, category, businesses),
        _service_predicates(term_candidates),
    ]
    return [group for group in groups if group]

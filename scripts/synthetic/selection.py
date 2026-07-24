"""Ağırlıklı rastgele seçim fonksiyonları: hizmet, cinsiyet, fiyat aralığı.

Tüm seçimler scripts/constants paketindeki sabitlerden yapılır, LLM
kullanılmaz.
"""

import random
from typing import Any

from scripts.constants import (
    DEFAULT_GENDER_PREFERENCE_WEIGHTS,
    GENDER_PREFERENCE_WEIGHTS,
    PRICE_RANGES_TL,
    QUERY_TERM_TO_TYPE,
    SERVICE_TAXONOMY,
)
from scripts.schemas import PriceRange

MIN_SERVICES_PER_BUSINESS: int = 3
MAX_SERVICES_PER_BUSINESS: int = 6
# İşletmenin kendi fiyat aralığı, kategori genişliğinin en az bu oranı kadar olsun
MIN_PRICE_GAP_RATIO: float = 0.15


def weighted_sample_without_replacement(pool: dict[str, int], k: int) -> list[str]:
    """Ağırlıklı, tekrarsız örnekleme (aynı öğe iki kez seçilmez)."""
    remaining = list(pool.items())
    selected: list[str] = []
    for _ in range(min(k, len(remaining))):
        names = [item[0] for item in remaining]
        weights = [item[1] for item in remaining]
        chosen = random.choices(names, weights=weights, k=1)[0]
        selected.append(chosen)
        remaining = [item for item in remaining if item[0] != chosen]
    return selected


def pick_services(type_normalized: str) -> list[str]:
    """İşletme tipine göre ağırlıklı, tekrarsız hizmet seçimi yapar."""
    count = random.randint(MIN_SERVICES_PER_BUSINESS, MAX_SERVICES_PER_BUSINESS)
    return weighted_sample_without_replacement(SERVICE_TAXONOMY[type_normalized], count)


def _largest_remainder_counts(weights: dict[str, float], total: int) -> dict[str, int]:
    """Ağırlık oranlarını, toplamı tam `total`'a eşit olan tamsayı sayılara çevirir
    (en büyük kalan yöntemi — yuvarlama nedeniyle toplamın kaymasını önler).
    """
    raw_counts = {key: weight * total for key, weight in weights.items()}
    counts = {key: int(value) for key, value in raw_counts.items()}
    remainder = total - sum(counts.values())
    ranked = sorted(raw_counts, key=lambda key: raw_counts[key] - counts[key], reverse=True)
    for i in range(remainder):
        counts[ranked[i % len(ranked)]] += 1
    return counts


def assign_genders(raw_records: list[dict[str, Any]]) -> dict[str, str]:
    """Cinsiyet etiketlerini kategori içinde katmanlı (stratified) dağıtır.

    Her işletmenin bağımsız zar atmasındansa, grubun toplam dağılımının
    hedef orana denk gelmesi garanti edilir — küçük örneklemde (örn. 20
    işletme) şansa bağlı "hepsi aynı çıktı" durumunu engeller.
    """
    place_ids_by_type: dict[str, list[str]] = {}
    for raw in raw_records:
        type_normalized = QUERY_TERM_TO_TYPE[raw["query_term"]]
        place_ids_by_type.setdefault(type_normalized, []).append(raw["place_id"])

    assignment: dict[str, str] = {}
    for type_normalized, place_ids in place_ids_by_type.items():
        weights = GENDER_PREFERENCE_WEIGHTS.get(type_normalized, DEFAULT_GENDER_PREFERENCE_WEIGHTS)
        counts = _largest_remainder_counts(weights, len(place_ids))
        labels = [gender for gender, count in counts.items() for _ in range(count)]
        random.shuffle(labels)
        random.shuffle(place_ids)
        for place_id, label in zip(place_ids, labels):
            assignment[place_id] = label
    return assignment


def pick_price_range(type_normalized: str) -> PriceRange:
    """Kategori sınırları içinde, işletmeye özgü rastgele bir alt-aralık üretir.

    Aksi halde aynı kategorideki tüm işletmeler birebir aynı fiyat
    aralığına sahip olurdu, bu da hem gerçekçi olmaz hem de fiyat bazlı
    tag'leri (uygun fiyatlı/premium) anlamsız kılardı.
    """
    category = PRICE_RANGES_TL[type_normalized]
    cat_min, cat_max = category["min"], category["max"]
    min_gap = max(1, int((cat_max - cat_min) * MIN_PRICE_GAP_RATIO))

    business_min = random.randint(cat_min, cat_max - min_gap)
    business_max = random.randint(business_min + min_gap, cat_max)
    return PriceRange(min=business_min, max=business_max)

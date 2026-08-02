"""`test_set.json`'daki mevcut soruları yüklem kümesine çevirip #4'ün ürettiği
yeni kombinasyonlarla çakışma kontrolünü sağlar (ADR-0027).

`time_of_day:*` etiketleri kasıtlı olarak yok sayılıyor — `predicates.py`
zaten `time_of_day`'i tek başına bir yüklem tipi olarak modellemiyor (tek
başına hiçbir şey filtrelemediği için, bkz. ADR-0027 #3), yani yeni motor
onunla eşleşen bir kombinasyon hiç üretmeyecek, karşılaştırmaya gerek yok.

`service_keyword:<terim>` karşılaştırması TEK bir kanonik lemma'ya
indirgenerek yapılamıyor — Zemberek belirsiz kelimeler için birden
fazla aday lemma döndürüyor (`"düğün"` -> {düğün, düğmek, düğü},
`"boşanma"` -> {boşanma, boşamak, boşanmak}) ve hangisinin
`predicates.py`'nin gerçekte ürettiği değerle eşleşeceği küme sırasına
göre değişir (gerçek veride bulundu: "ilkini kanonik kabul et"
yaklaşımı Fotoğrafçı/"düğün" ve Avukat/"boşanma" için yanlış lemma'yı
seçip çakışmayı kaçırdı). Doğrusu — terim eşleştirmedeki aynı kural
(`turkish_lemma.py`) — küme KESİŞİMİ: bir yüklem, karşı taraftaki aday
kümeyle herhangi bir ortak elemanı varsa eşleşir.
"""

import json
from pathlib import Path

from scripts.ragas_testset.combination_search import ViableCombination
from scripts.ragas_testset.turkish_lemma import lemmas_of

_WEEKDAY_NAMES: frozenset[str] = frozenset(
    {"pazartesi", "salı", "çarşamba", "perşembe", "cuma"}
)

# Bir yüklem slotu: (tip, o slotu dolduran kabul edilebilir değerler kümesi).
# Servis dışı tipler için tek elemanlı bir küme, servis için `lemmas_of`'un
# döndürdüğü tüm aday lemma'lar.
PredicateSlot = tuple[str, frozenset[str]]


def _day_bucket_from_tag(day_name: str) -> str:
    if day_name in _WEEKDAY_NAMES:
        return "weekday"
    if day_name == "cumartesi":
        return "saturday"
    return "sunday"


def _tag_to_slot(tag: str) -> PredicateSlot | None:
    """Bir `intent_tags` girdisini bir yüklem slotuna çevirir; modellenmeyen etiketler için None döner."""
    if tag.startswith("gender:"):
        return ("gender", frozenset({tag.split(":", 1)[1]}))
    if tag == "online_only":
        return ("online", frozenset({"online"}))
    if tag == "weekend_open_only":
        return ("day", frozenset({"weekend_open"}))
    if tag.startswith("day_of_week:"):
        return ("day", frozenset({_day_bucket_from_tag(tag.split(":", 1)[1])}))
    if tag.startswith("price_preference:"):
        return ("price", frozenset({tag.split(":", 1)[1]}))
    if tag.startswith("service_keyword:"):
        keyword = tag.split(":", 1)[1]
        return ("service", lemmas_of(keyword))
    return None


def load_existing_predicate_sets(
    test_set_path: Path,
) -> dict[str, set[frozenset[PredicateSlot]]]:
    """Kategori bazlı, mevcut soruların yüklem slot kümelerini döner."""
    questions = json.loads(test_set_path.read_text(encoding="utf-8"))
    by_category: dict[str, set[frozenset[PredicateSlot]]] = {}
    for question in questions:
        category = question.get("category")
        if category is None:
            continue  # multi_category_ambiguous / out_of_scope kategorisiz sorular
        slot_set = frozenset(
            slot
            for tag in question["intent_tags"]
            if (slot := _tag_to_slot(tag)) is not None
        )
        by_category.setdefault(category, set()).add(slot_set)
    return by_category


def _slots_match(
    combo_slots: list[PredicateSlot], existing_slots: list[PredicateSlot]
) -> bool:
    """Her combo slotu, existing_slots'ta AYNI tipte ve DEĞER KESİŞİMİ olan tam olarak bir slotla eşleşmeli."""
    if len(combo_slots) != len(existing_slots):
        return False
    remaining = list(existing_slots)
    for combo_type, combo_values in combo_slots:
        match_index = next(
            (
                i
                for i, (existing_type, existing_values) in enumerate(remaining)
                if existing_type == combo_type and combo_values & existing_values
            ),
            None,
        )
        if match_index is None:
            return False
        remaining.pop(match_index)
    return True


def is_duplicate(
    combination: ViableCombination, existing: set[frozenset[PredicateSlot]]
) -> bool:
    """Bir kombinasyonun mevcut sorulardan biriyle (lemma kesişimi anlamında) aynı yüklem kümesini üretip üretmediğini kontrol eder."""
    combo_slots = [
        (predicate.type_name, frozenset({predicate.value_name}))
        for predicate in combination.components
    ]
    return any(
        _slots_match(combo_slots, list(existing_set)) for existing_set in existing
    )

"""scripts/ragas_testset/existing_coverage.py için birim testler.

`test_search_combinations` çalıştırılırken gerçek veride bulunan bir
hatanın regresyon testi: `service_keyword` etiketleri, Zemberek'in
birden fazla aday lemma döndürdüğü belirsiz kelimeler için ("düğün" ->
{düğün, düğmek, düğü}) TEK bir kanonik lemma'ya indirgenerek
karşılaştırılınca, `predicates.py`'nin gerçekte ürettiği değerle
çakışma kaçırılabiliyordu — doğrusu küme kesişimi.
"""

from scripts.ragas_testset.combination_search import ViableCombination
from scripts.ragas_testset.coverage_stats import evaluate_split
from scripts.ragas_testset.existing_coverage import is_duplicate
from scripts.ragas_testset.predicates import Predicate


def _combination(*components: Predicate) -> ViableCombination:
    matched_ids = frozenset({1, 2, 3})
    return ViableCombination(
        components=list(components),
        matched_ids=matched_ids,
        split=evaluate_split(len(matched_ids), 10),
    )


def test_is_duplicate_matches_ambiguous_lemma_via_intersection() -> None:
    """'düğün' etiketi, predicates.py'nin 'düğmek' lemma'sını üretse bile
    (Zemberek ikisini de aynı kelimenin aday lemma'sı sayıyor) çakışma
    olarak tespit edilmeli — tek kanonik lemma seçimi bunu kaçırıyordu."""
    combo = _combination(
        Predicate(
            type_name="service", value_name="düğmek", matched_ids=frozenset({1, 2, 3})
        )
    )
    existing = {frozenset({("service", frozenset({"düğün", "düğmek", "düğü"}))})}

    assert is_duplicate(combo, existing) is True


def test_is_duplicate_false_when_no_lemma_overlap() -> None:
    combo = _combination(
        Predicate(
            type_name="service", value_name="fıtık", matched_ids=frozenset({1, 2, 3})
        )
    )
    existing = {frozenset({("service", frozenset({"boyamak"}))})}

    assert is_duplicate(combo, existing) is False


def test_is_duplicate_requires_same_number_of_predicates() -> None:
    """Tek yüklemli bir kombinasyon, iki yüklemli mevcut bir soruyla eşleşmemeli."""
    combo = _combination(
        Predicate(
            type_name="day", value_name="saturday", matched_ids=frozenset({1, 2, 3})
        )
    )
    existing = {
        frozenset(
            {
                ("day", frozenset({"saturday"})),
                ("price", frozenset({"cheap"})),
            }
        )
    }

    assert is_duplicate(combo, existing) is False


def test_is_duplicate_matches_multi_predicate_combination_regardless_of_order() -> None:
    combo = _combination(
        Predicate(
            type_name="price", value_name="cheap", matched_ids=frozenset({1, 2, 3})
        ),
        Predicate(
            type_name="day", value_name="saturday", matched_ids=frozenset({1, 2, 3})
        ),
    )
    existing = {
        frozenset(
            {
                ("day", frozenset({"saturday"})),
                ("price", frozenset({"cheap"})),
            }
        )
    }

    assert is_duplicate(combo, existing) is True

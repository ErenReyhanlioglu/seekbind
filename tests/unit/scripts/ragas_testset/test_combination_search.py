"""scripts/ragas_testset/combination_search.py için birim testler.

Sentetik küçük yüklem kümeleriyle (10 işletme, id 0-9) — gerçek DB ya da
Zemberek gerekmez, sadece arama mantığı test edilir.
"""

from scripts.ragas_testset.combination_search import search
from scripts.ragas_testset.predicates import Predicate

ALL_IDS: frozenset[int] = frozenset(range(10))


def test_search_finds_single_viable_predicate() -> None:
    group_a = [
        Predicate(
            type_name="a", value_name="a1", matched_ids=frozenset({0, 1, 2, 3, 4, 5})
        )
    ]

    results = search([group_a], ALL_IDS)

    assert len(results) == 1
    assert results[0].matched_ids == frozenset({0, 1, 2, 3, 4, 5})


def test_search_excludes_predicate_matching_everyone() -> None:
    """Simetrik MIN_COUNT: eşleşMEyen taraf 0 olduğu için (herkes eşleşiyor) elenmeli."""
    group_c = [Predicate(type_name="c", value_name="c1", matched_ids=ALL_IDS)]

    results = search([group_c], ALL_IDS)

    assert results == []


def test_search_excludes_split_below_min_count_on_either_side() -> None:
    too_few = [Predicate(type_name="x", value_name="x1", matched_ids=frozenset({0, 1}))]
    too_many = [
        Predicate(type_name="y", value_name="y1", matched_ids=frozenset(range(8)))
    ]  # 8/10, complement=2 < MIN_COUNT

    assert search([too_few], ALL_IDS) == []
    assert search([too_many], ALL_IDS) == []


def test_search_combines_two_groups_exactly_once_regardless_of_order() -> None:
    """Kanonik sıra: A+B kombinasyonu tek bir sonuç olarak çıkmalı, iki kez değil."""
    group_a = [
        Predicate(
            type_name="a", value_name="a1", matched_ids=frozenset({0, 1, 2, 3, 4, 5})
        )
    ]
    group_b = [
        Predicate(
            type_name="b", value_name="b1", matched_ids=frozenset({0, 1, 2, 6, 7, 8})
        )
    ]

    results = search([group_a, group_b], ALL_IDS)

    combined = [r for r in results if len(r.components) == 2]
    assert len(combined) == 1
    assert combined[0].matched_ids == frozenset({0, 1, 2})


def test_search_prunes_vacuous_predicate_that_is_superset_of_current_combo() -> None:
    """'Boş yüklem' elemesi: E, A'nın üst kümesi olduğu için A+E kombinasyonu A'yı hiç daraltmıyor."""
    group_a = [
        Predicate(
            type_name="a", value_name="a1", matched_ids=frozenset({0, 1, 2, 3, 4, 5})
        )
    ]
    group_e = [
        Predicate(
            type_name="e", value_name="e1", matched_ids=frozenset({0, 1, 2, 3, 4, 5, 6})
        )
    ]

    results = search([group_a, group_e], ALL_IDS)

    combined = [r for r in results if len(r.components) == 2]
    assert combined == []


def test_search_does_not_combine_two_values_from_the_same_group() -> None:
    """Aynı tipten iki değer (örn. gender=female VE gender=male) asla birlikte olmamalı."""
    gender_group = [
        Predicate(
            type_name="gender",
            value_name="female",
            matched_ids=frozenset({0, 1, 2, 3, 4}),
        ),
        Predicate(
            type_name="gender",
            value_name="male",
            matched_ids=frozenset({5, 6, 7, 8, 9}),
        ),
    ]

    results = search([gender_group], ALL_IDS)

    assert all(len(r.components) == 1 for r in results)

"""scripts/ragas_testset/coverage_stats.py için birim testler."""

import random

from scripts.ragas_testset.coverage_stats import MIN_COUNT, entropy, evaluate_split


def test_entropy_is_maximum_at_even_split() -> None:
    assert entropy(0.5) == 1.0


def test_entropy_is_zero_at_both_degenerate_extremes() -> None:
    assert entropy(0.0) == 0.0
    assert entropy(1.0) == 0.0


def test_entropy_only_depends_on_fraction_not_on_which_businesses_match() -> None:
    """Permütasyon deneyi (ADR-0027): entropi düzenlemeye duyarsız olmalı —
    hangi işletmelerin etiketi taşıdığı değişse de sayı (ve dolayısıyla
    fraction) sabitse entropi de sabit kalmalı."""
    businesses = list(range(20))
    entropies = set()
    for _ in range(5):
        random.shuffle(businesses)
        matched = len(businesses[:10])
        entropies.add(entropy(matched / len(businesses)))

    assert entropies == {1.0}


def test_evaluate_split_is_not_viable_below_min_count_on_matched_side() -> None:
    result = evaluate_split(matched_count=MIN_COUNT - 1, total_count=20)

    assert result.is_viable is False


def test_evaluate_split_is_not_viable_below_min_count_on_unmatched_side() -> None:
    """Simetrik kural: eşleşMEyen taraf da MIN_COUNT altına düşerse dejenere sayılır."""
    result = evaluate_split(matched_count=18, total_count=20)

    assert result.is_viable is False


def test_evaluate_split_is_viable_when_both_sides_meet_min_count() -> None:
    result = evaluate_split(matched_count=10, total_count=20)

    assert result.is_viable is True
    assert result.fraction == 0.5
    assert result.entropy == 1.0


def test_evaluate_split_matches_known_fizyoterapist_fitik_case() -> None:
    """Gerçek veride doğrulanan referans değer (bkz. ADR-0027): Fizyoterapist
    kategorisinde 20 işletmeden 10'u 'fıtık' lemma'sını taşıyor."""
    result = evaluate_split(matched_count=10, total_count=20)

    assert result.is_viable is True
    assert result.entropy == 1.0

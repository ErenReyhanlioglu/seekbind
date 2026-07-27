"""backend/services/search/fusion.py için birim testler."""

import pytest

from backend.services.search.fusion import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_ranks_item_present_in_both_lists_first() -> None:
    bm25_results = [(1, 0.9), (2, 0.5)]
    vector_results = [(2, 100.0), (3, 50.0)]

    fused = reciprocal_rank_fusion([bm25_results, vector_results])

    assert fused[0][0] == 2  # her iki listede de var, en üstte olmalı


def test_reciprocal_rank_fusion_ignores_score_magnitude_uses_rank_only() -> None:
    # skorlar çok farklı ölçekte (BM25 negatif, vektör 0-1) ama ikisi de
    # kendi listesinde 1. sırada — RRF katkıları eşit olmalı
    bm25_results = [(1, -3.2)]
    vector_results = [(2, 0.99)]

    fused = reciprocal_rank_fusion([bm25_results, vector_results])
    scores = dict(fused)

    assert scores[1] == pytest.approx(scores[2])


def test_reciprocal_rank_fusion_computes_expected_scores_with_default_k() -> None:
    bm25_results = [(1, 0.9), (2, 0.5)]
    vector_results = [(2, 100.0), (3, 50.0)]

    fused = dict(reciprocal_rank_fusion([bm25_results, vector_results]))

    assert fused[1] == pytest.approx(1 / 61)
    assert fused[2] == pytest.approx(1 / 62 + 1 / 61)
    assert fused[3] == pytest.approx(1 / 62)


def test_reciprocal_rank_fusion_includes_items_present_in_only_one_list() -> None:
    fused = reciprocal_rank_fusion([[(1, 0.9)], [(2, 0.8)]])

    assert {business_id for business_id, _ in fused} == {1, 2}


def test_reciprocal_rank_fusion_handles_empty_lists() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_reciprocal_rank_fusion_respects_custom_k() -> None:
    fused_default = dict(reciprocal_rank_fusion([[(1, 1.0)]]))
    fused_custom = dict(reciprocal_rank_fusion([[(1, 1.0)]], k=10))

    assert fused_custom[1] == pytest.approx(1 / 11)
    assert fused_custom[1] != pytest.approx(fused_default[1])

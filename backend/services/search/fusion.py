"""Reciprocal Rank Fusion (RRF) — farklı arama yöntemlerinin sıralı
sonuç listelerini, skorların büyüklüğüne değil sırasına (rank) göre birleştirir.
"""

RRF_K: int = 60


def reciprocal_rank_fusion(
    result_lists: list[list[tuple[int, float]]],
    k: int = RRF_K,
) -> list[tuple[int, float]]:
    """Birden fazla sıralı (business_id, skor) listesini RRF ile birleştirir.

    Her listedeki skorun büyüklüğü yok sayılır, sadece o listede kaçıncı
    sırada olduğu (rank) kullanılır — BM25 (negatif olabilen) ve vektör
    (0-1 arası cosine) skorları farklı ölçeklerde olduğu için doğrudan
    toplanamaz/karşılaştırılamaz, ama rank her zaman karşılaştırılabilir.

    rrf_score(id) = Σ 1 / (k + rank), her listedeki rank'ler toplanır.
    Bir id birden fazla listede geçiyorsa katkılar toplanır (daha yüksek
    skor); sadece bir listede geçiyorsa tek katkı alır, sıfırlanmaz.
    """
    fused_scores: dict[int, float] = {}
    for results in result_lists:
        for rank, (business_id, _) in enumerate(results, start=1):
            fused_scores[business_id] = fused_scores.get(business_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused_scores.items(), key=lambda pair: pair[1], reverse=True)

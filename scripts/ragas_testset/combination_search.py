"""Apriori-tarzı çok-yüklemli kombinasyon araması (problem #4, ADR-0027).

Sabit bir derinlik yok — bir kombinasyon MIN_COUNT'un altına düşerse
üzerine yeni yüklem eklemenin (downward closure: sayı sadece küçülebilir)
anlamı kalmaz, o dal budanır. Gerçek veride (27 kategorinin tamamı)
bulunan iki ek kural olmadan Fizyoterapist'te 110 sahte "kombinasyon"
çıkmıştı, gerçekte 26'ymış:

- **Kanonik sıra:** yüklem grupları sadece kendisinden SONRAKİ gruplarla
  genişletiliyor (`start_index` ilerletme) — aynı kombinasyon iki farklı
  sırada iki kez üretilmiyor.
- **"Boş yüklem" elemesi:** eklenen her yüklem, o ANDAKİ kombinasyonun
  eşleşen kümesini gerçekten daraltmalı — daraltmıyorsa (örn. üst
  kümesiyse) o yüklem kombinasyonda gereksiz/aldatıcı duruyor demektir.

Cross-type collinearity (örn. weekend_open==saturday) burada değil,
`predicates.py`'de kaynağında (gün tipi kendi içinde) elenir — genel bir
"her çift grup için küme eşitliği kontrolü" burada kasıtlı olarak
uygulanmıyor, gözlemlenen tek örnek gün tipinin kendi içindeydi.
"""

from pydantic import BaseModel

from scripts.ragas_testset.coverage_stats import SplitResult, evaluate_split
from scripts.ragas_testset.predicates import Predicate


class ViableCombination(BaseModel):
    """MIN_COUNT'u simetrik geçen, her yüklemi gerçekten daraltan bir kombinasyon."""

    components: list[Predicate]
    matched_ids: frozenset[int]
    split: SplitResult


def _search_from(
    predicate_groups: list[list[Predicate]],
    start_index: int,
    combo: list[Predicate],
    matched_ids: frozenset[int],
    total_count: int,
    results: list[ViableCombination],
) -> None:
    for group_index in range(start_index, len(predicate_groups)):
        for predicate in predicate_groups[group_index]:
            new_matched = matched_ids & predicate.matched_ids
            if len(new_matched) >= len(matched_ids):
                continue  # boş yüklem: bu değer mevcut kombinasyonu hiç daraltmadı
            split = evaluate_split(len(new_matched), total_count)
            if not split.is_viable:
                continue
            new_combo = [*combo, predicate]
            results.append(
                ViableCombination(
                    components=new_combo, matched_ids=new_matched, split=split
                )
            )
            _search_from(
                predicate_groups,
                group_index + 1,
                new_combo,
                new_matched,
                total_count,
                results,
            )


def search(
    predicate_groups: list[list[Predicate]], all_business_ids: frozenset[int]
) -> list[ViableCombination]:
    """Verilen yüklem gruplarından tüm geçerli kombinasyonları bulur, entropiye göre sıralı."""
    results: list[ViableCombination] = []
    _search_from(
        predicate_groups, 0, [], all_business_ids, len(all_business_ids), results
    )
    results.sort(key=lambda combination: -combination.split.entropy)
    return results

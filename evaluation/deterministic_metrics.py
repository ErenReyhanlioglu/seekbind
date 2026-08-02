"""RAGAS'ın LLM-yargıcından bağımsız, salt ID karşılaştırmasına dayanan
deterministik metrikler — ekstra API çağrısı gerektirmez, aynı trace'lerden
(gerçek pipeline'ın döndürdüğü işletme id'leri + `test_set.json`'daki
`expected_business_ids`) hesaplanır.

`ragas_metrics.py`'nin (LLM-yargıç tabanlı Faithfulness/Answer Relevancy/
Context Precision/Recall) tamamlayıcısı — RAGAS'ın cümle-bazlı entailment
ölçümünden daha katı ve doğrudan yorumlanabilir bir sinyal verir (bkz.
`evaluation/results/ragas/.../pipeline_quality_check_log.md`'deki manuel
doğrulamanın otomatikleştirilmiş hali).

`expected_empty` etiketli sorular (context'siz dönmesi GEREKEN sorular) diğer
6 metrikten hariç tutulup ayrı raporlanır — aynı ADR-0009 (2026-08-01
güncellemesi) segmentasyon mantığı, RAGAS'ın kendi Context Precision/Recall'u
için de kullanılıyor.

`recall_at_k`'nin paydası ham `len(expected_business_ids)` DEĞİL,
`min(RECOMMENDATION_RESULT_LIMIT, len(expected_business_ids))` — beklenen
küme gösterim limitinden büyükse (örn. N=15, K=5) ham N'e bölmek, sistem en
mükemmel 5 sonucu getirse bile skoru yapısal olarak %33'te tavana çarptırır,
bu da retrieval kalitesini değil sadece gösterim limitini ölçer.
"""

from backend.services.rag.recommendation import RECOMMENDATION_RESULT_LIMIT
from evaluation.ragas_traces import EXPECTED_EMPTY_TAG


def _best_rank(result_ids: list[int], expected: set[int]) -> int | None:
    for rank, business_id in enumerate(result_ids, start=1):
        if business_id in expected:
            return rank
    return None


def _top1_accuracy(traces: list[dict]) -> float:
    correct = sum(
        1
        for t in traces
        if t["result_ids"] and t["result_ids"][0] in set(t["expected_business_ids"])
    )
    return correct / len(traces)


def _pooled_context_precision(traces: list[dict]) -> float:
    """Gösterilen TÜM işletmeler havuzda birleştirilip tek bir oran hesaplanır
    (micro-average) — büyük `expected_business_ids` kümeli sorular daha çok
    ağırlık taşır; `precision_at_k` (soru-bazlı ortalama, macro) kasıtlı
    olarak farklı bir bakış açısı sunar, ikisi birlikte raporlanır."""
    total_shown = sum(len(t["result_ids"]) for t in traces)
    total_correct = sum(
        len(set(t["result_ids"]) & set(t["expected_business_ids"])) for t in traces
    )
    return total_correct / total_shown if total_shown else 0.0


def _mrr(traces: list[dict]) -> float:
    reciprocal_ranks = [
        1.0 / rank if rank else 0.0
        for rank in (
            _best_rank(t["result_ids"], set(t["expected_business_ids"])) for t in traces
        )
    ]
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def _hit_rate_at_k(traces: list[dict]) -> float:
    """`recall_at_k`'den farkı: NE KADARINI değil, HİÇ mi bulduk'u ölçer —
    top-K'da beklenen kümeden en az bir işletme varsa 1, yoksa 0 (ikili).
    Büyük `expected_business_ids` kümeli sorularda recall düşük çıksa bile
    ("hepsini gösteremedik") hit rate yüksek kalabilir ("en azından biri
    doğruydu") — ikisi birbirini tamamlar, biri diğerinin yerini tutmaz."""
    hits = sum(
        1 for t in traces if set(t["result_ids"]) & set(t["expected_business_ids"])
    )
    return hits / len(traces)


def _recall_at_k(traces: list[dict]) -> float:
    per_question = []
    for t in traces:
        expected = set(t["expected_business_ids"])
        found = len(set(t["result_ids"]) & expected)
        denominator = min(RECOMMENDATION_RESULT_LIMIT, len(expected))
        per_question.append(found / denominator if denominator else 0.0)
    return sum(per_question) / len(per_question)


def _precision_at_k(traces: list[dict]) -> float:
    per_question = []
    for t in traces:
        expected = set(t["expected_business_ids"])
        found = len(set(t["result_ids"]) & expected)
        shown = len(t["result_ids"])
        per_question.append(found / shown if shown else 0.0)
    return sum(per_question) / len(per_question)


def _expected_empty_accuracy(traces: list[dict]) -> float | None:
    empty_traces = [t for t in traces if EXPECTED_EMPTY_TAG in t["intent_tags"]]
    if not empty_traces:
        return None  # bu koşumda hiç expected_empty soru yoksa (örn. küçük pilot)
    correct = sum(1 for t in empty_traces if not t["result_ids"])
    return correct / len(empty_traces)


def compute_deterministic_metrics(traces: list[dict]) -> dict[str, float | None]:
    """7 deterministik metriği hesaplayıp tek bir sözlükte döner.

    `traces`'in `result_ids`/`expected_business_ids` içermesi gerekir (bkz.
    `ragas_traces.py`) — eski trace dosyalarında (bu alanlar eklenmeden önce
    kaydedilmiş) `KeyError` fırlatır, sessizce eksik/yanlış rapor vermez.
    """
    non_empty = [t for t in traces if EXPECTED_EMPTY_TAG not in t["intent_tags"]]
    metrics: dict[str, float | None] = {
        "expected_empty_accuracy": _expected_empty_accuracy(traces),
    }
    if non_empty:
        metrics["top1_accuracy"] = _top1_accuracy(non_empty)
        metrics["pooled_context_precision"] = _pooled_context_precision(non_empty)
        metrics["mrr"] = _mrr(non_empty)
        metrics[f"hit_rate_at_{RECOMMENDATION_RESULT_LIMIT}"] = _hit_rate_at_k(
            non_empty
        )
        metrics[f"recall_at_{RECOMMENDATION_RESULT_LIMIT}"] = _recall_at_k(non_empty)
        metrics[f"precision_at_{RECOMMENDATION_RESULT_LIMIT}"] = _precision_at_k(
            non_empty
        )
    return metrics

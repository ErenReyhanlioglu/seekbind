"""RAGAS'ta top-1'i yanlış çıkan sorularda, doğru işletmenin hangi pipeline
aşamasında kaybolduğunu/gerilediğini bulan tanı script'i.

`evaluation/test_set.json`'daki `expected_business_ids`'i, `search_providers()`
(bkz. `backend/services/search/service.py`) içindeki her ara aşamada (vektör,
BM25, RRF füzyon havuzu, müsaitlik filtresi, reranker, rating/mesafe son
sıralaması) ayrı ayrı arar — hangi aşamada "en iyi beklenen sıra" kötüleşiyor
görmek için. `evaluation/ragas_eval.py`'nin aksine RAGAS metriği hesaplamaz,
LLM'in son öneri metnini de üretmez (`generate_recommendation()` — pahalı,
temperature=0.7, cache'siz — hiç çağrılmaz); sadece arama/sıralama
aşamalarına bakar.

Gerçek Postgres/Qdrant/reranker'a (Jina) karşı çalışır — intent parsing için
gerçek bir LLM çağrısı (ucuz, kısa JSON) ve embedding için gerçek bir
OpenAI/Ollama çağrısı yapılır (cache'siz, `evaluation/ragas_eval.py`'nin
COMBOS'uyla aynı ham sağlayıcılar kullanılır — hangi kombinasyonun
sonuçlarını inceliyorsak onunla tutarlı olsun diye).

Kullanım:
    uv run python -m scripts.diagnostics.diagnose_ranking_stages \
        --ids q009,q033,q034 [--combo openai-openai] [etiket]
"""

import argparse
import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import DEMO_REFERENCE_TODAY
from backend.db.models import Business
from backend.db.qdrant import get_qdrant_client
from backend.db.session import get_session_factory
from backend.services.embedding import (
    EmbeddingProvider,
    OllamaEmbedding,
    OpenAIEmbedding,
)
from backend.services.llm import LLMProvider, OllamaLLM, OpenAILLM
from backend.services.rag.intent import (
    IntentParsingError,
    build_availability_filter,
    build_search_filters,
    parse_intent,
)
from backend.services.rag.recommendation import RECOMMENDATION_RESULT_LIMIT
from backend.services.search import (
    BM25Index,
    RatingPreference,
    RerankerProvider,
    apply_final_sort,
    fetch_available_business_ids,
    get_reranker_provider,
    reciprocal_rank_fusion,
    translate_filters_to_qdrant,
    vector_search,
)
from backend.services.search.service import (
    CANDIDATE_DEPTH_PER_SOURCE,
    CANDIDATE_POOL_SIZE,
    _fetch_businesses_by_id,
    _rerank_businesses,
)
from backend.services.search.vector import fetch_filtered_business_ids
from scripts.diagnostics._result_paths import build_results_dir

logger = logging.getLogger(__name__)

TEST_SET_PATH: Path = Path("evaluation/test_set.json")
EXPERIMENT_NAME: str = "ranking_stage_diagnosis"
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"  # Windows dosya sisteminde ":" geçersiz

ComboName = Literal["openai-openai", "openai-ollama", "ollama-openai", "ollama-ollama"]
# evaluation/ragas_eval.py'deki COMBOS ile aynı 2x2 ızgara — burada ayrı
# tanımlanır çünkü scripts/ paketi evaluation/'a bağımlı değil (tersi doğru
# yön), 4 satırlık bir mapping için bu ayrımı bozmaya değmez.
COMBOS: dict[ComboName, tuple[type[LLMProvider], type[EmbeddingProvider]]] = {
    "openai-openai": (OpenAILLM, OpenAIEmbedding),
    "openai-ollama": (OpenAILLM, OllamaEmbedding),
    "ollama-openai": (OllamaLLM, OpenAIEmbedding),
    "ollama-ollama": (OllamaLLM, OllamaEmbedding),
}


def _best_rank(ordered_ids: list[int], expected: set[int]) -> int | None:
    """Sıralı id listesinde beklenen kümeden ilk (en iyi) rastlanan sırayı döner."""
    for rank, business_id in enumerate(ordered_ids, start=1):
        if business_id in expected:
            return rank
    return None


async def _lookup_titles(session: AsyncSession, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    result = await session.execute(
        select(Business.id, Business.title).where(Business.id.in_(ids))
    )
    return {business_id: title for business_id, title in result.all()}


def _load_selected_questions(ids: list[str]) -> list[dict]:
    """`test_set.json`'dan sadece verilen id'lere ait soruları döner.

    Bilinmeyen bir id verilirse sessizce atlamak yerine hemen hata fırlatır
    (fail fast) — yazım hatası içeren bir id'nin sessizce yok sayılması,
    "17 soru istedim ama 16 sonuç geldi" gibi fark edilmesi zor bir hataya
    yol açardı.
    """
    questions = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in questions}
    missing = [qid for qid in ids if qid not in by_id]
    if missing:
        raise ValueError(f"test_set.json'da bulunamayan id'ler: {missing}")
    return [by_id[qid] for qid in ids]


async def _generate_candidates(
    qdrant_client: AsyncQdrantClient,
    embedding_provider: EmbeddingProvider,
    bm25_index: BM25Index,
    semantic_query: str,
    qdrant_filter: Filter | None,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]], list[int]]:
    """Vektör + BM25 aday üretimi ve RRF füzyonu — (vektör ham, BM25 ham,
    füzyon sonrası aday id havuzu) döner; `search_providers()`'ın 1-3 arası
    aşamalarının birebir aynısı."""
    vector_results = await vector_search(
        qdrant_client,
        embedding_provider,
        semantic_query,
        CANDIDATE_DEPTH_PER_SOURCE,
        qdrant_filter,
    )
    bm25_results = bm25_index.search(semantic_query, CANDIDATE_DEPTH_PER_SOURCE)
    if qdrant_filter is not None:
        filtered_ids = await fetch_filtered_business_ids(
            qdrant_client, embedding_provider, qdrant_filter
        )
        bm25_results = [pair for pair in bm25_results if pair[0] in filtered_ids]
    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    candidate_ids = [business_id for business_id, _ in fused][:CANDIDATE_POOL_SIZE]
    return vector_results, bm25_results, candidate_ids


async def _rerank_and_sort(
    session: AsyncSession,
    reranker_provider: RerankerProvider,
    candidate_ids: list[int],
    semantic_query: str,
    rating_preference: RatingPreference | None,
    online_only: bool,
    expected: set[int],
    stages: dict[str, int | None],
) -> list[Business]:
    """Reranker + (varsa) rating son sıralamasını uygular, `stages`'ı 5/6
    numaralı aşamalarla günceller (yerinde), son işletme listesini döner.

    `_rerank_businesses` (private) bilerek doğrudan kullanılıyor: production
    ile birebir aynı fonksiyon — reranker hata verirse RRF sırasına düşen
    graceful degradation'ı da dahil, ayrı bir kopyasını yazıp davranıştan
    sapma riski almamak için.
    """
    candidates = await _fetch_businesses_by_id(session, candidate_ids)
    candidates = await _rerank_businesses(reranker_provider, semantic_query, candidates)
    stages["5_post_rerank"] = _best_rank([b.id for b in candidates], expected)

    if rating_preference is not None:
        candidates = apply_final_sort(
            candidates,
            rating_preference,
            None,
            online_exempt_from_distance=not online_only,
        )
        stages["6_post_final_sort"] = _best_rank([b.id for b in candidates], expected)
    return candidates


async def _diagnose_question(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    llm_provider: LLMProvider,
    reranker_provider: RerankerProvider,
    question: dict,
    today: date,
) -> dict:
    """Bir soru için tüm pipeline aşamalarını çalıştırıp her aşamada
    beklenen işletmenin en iyi sırasını (`stage_best_rank_of_expected`) döner."""
    expected = set(question["expected_business_ids"])
    intent, _cache_hit = await parse_intent(llm_provider, question["question"], today)
    filters = await build_search_filters(intent, session)
    availability = build_availability_filter(intent, today)
    qdrant_filter = translate_filters_to_qdrant(filters)

    vector_results, bm25_results, candidate_ids = await _generate_candidates(
        qdrant_client,
        embedding_provider,
        bm25_index,
        intent.semantic_query,
        qdrant_filter,
    )
    stages: dict[str, int | None] = {
        "1_vector_only": _best_rank([bid for bid, _ in vector_results], expected),
        "2_bm25_only": _best_rank([bid for bid, _ in bm25_results], expected),
        "3_rrf_candidate_pool": _best_rank(candidate_ids, expected),
    }
    if availability is not None:
        available_ids = await fetch_available_business_ids(
            session, candidate_ids, availability
        )
        candidate_ids = [bid for bid in candidate_ids if bid in available_ids]
        stages["4_post_availability"] = _best_rank(candidate_ids, expected)

    candidates = await _rerank_and_sort(
        session,
        reranker_provider,
        candidate_ids,
        intent.semantic_query,
        intent.rating_preference,
        filters.online_only,
        expected,
        stages,
    )
    final_top: list[Business] = candidates[:RECOMMENDATION_RESULT_LIMIT]
    stages["7_final_top_shown"] = _best_rank([b.id for b in final_top], expected)

    titles = await _lookup_titles(session, sorted(expected) + [b.id for b in final_top])
    return {
        "id": question["id"],
        "question": question["question"],
        "semantic_query": intent.semantic_query,
        "category_filter": filters.category,
        "rating_preference": intent.rating_preference,
        "expected_ids": sorted(expected),
        "stage_best_rank_of_expected": stages,
        "final_top_ids": [b.id for b in final_top],
        "final_top_titles": [titles.get(b.id, "?") for b in final_top],
        "final_top1_correct": bool(final_top) and final_top[0].id in expected,
    }


def _write_result(
    records: list[dict], label: str | None, llm_model: str, embedder_model: str
) -> Path:
    results_dir = build_results_dir(EXPERIMENT_NAME, embedder_model, llm_model)
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    filename = f"{label}_{timestamp}.json" if label else f"{timestamp}.json"
    output_path = results_dir / filename
    output_path.write_text(
        json.dumps({"records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


async def main(ids: list[str], combo_name: ComboName, label: str | None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    questions = _load_selected_questions(ids)

    llm_cls, embedding_cls = COMBOS[combo_name]
    llm_provider = llm_cls()
    embedding_provider = embedding_cls()
    reranker_provider = get_reranker_provider()
    qdrant_client = get_qdrant_client()
    session_factory = get_session_factory()
    bm25_index = BM25Index()

    records: list[dict] = []
    try:
        async with session_factory() as session:
            await bm25_index.refresh_if_stale(session)
            for question in questions:
                try:
                    record = await _diagnose_question(
                        session,
                        qdrant_client,
                        bm25_index,
                        embedding_provider,
                        llm_provider,
                        reranker_provider,
                        question,
                        DEMO_REFERENCE_TODAY,
                    )
                except IntentParsingError as e:
                    logger.warning(
                        "%s atlandı, intent parsing başarısız: %s", question["id"], e
                    )
                    continue
                records.append(record)
                logger.info(
                    "%s: top1_correct=%s stages=%s",
                    record["id"],
                    record["final_top1_correct"],
                    record["stage_best_rank_of_expected"],
                )
    finally:
        await llm_provider.close()
        await embedding_provider.close()
        await reranker_provider.close()

    output_path = _write_result(
        records, label, llm_provider.model, embedding_provider.model
    )
    logger.info("Sonuçlar kaydedildi: %s", output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ids",
        required=True,
        help="Virgülle ayrılmış test_set.json soru id'leri (örn. q009,q033,q034)",
    )
    parser.add_argument(
        "--combo",
        choices=list(COMBOS.keys()),
        default="openai-openai",
        help="Hangi LLM x embedding kombinasyonuyla çalıştırılsın",
    )
    parser.add_argument(
        "label", nargs="?", default=None, help="Sonuç dosyası adına eklenecek etiket"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.ids.split(","), args.combo, args.label))

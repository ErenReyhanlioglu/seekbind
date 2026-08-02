"""Kayıtlı trace'lerden RAGAS'ın 4 metriğini (Faithfulness, Answer Relevancy,
Context Precision, Context Recall) hesaplama.

`evaluation/ragas_eval.py`'nin ikinci aşaması — `evaluation/ragas_traces.py`
tarafından üretilen (question, answer, contexts, reference) trace'lerini
girdi alır. Ayrı tutulması, evaluator modelde değişiklik ya da yeni bir
metrik eklenirse pipeline'ı BAŞTAN çalıştırmadan sadece bu adımın tekrar
çalıştırılabilmesini sağlar.

Context Recall/Precision, `expected_empty` etiketli sorularda (context boş
olduğu için) anlamsız kalabilir — bkz. ADR-0009'un 2026-08-01 güncellemesi.
Bu yüzden bu 2 metrik için hem tüm sorunun hem de bu etiketlileri hariç
tutan alt kümenin ortalaması ayrı ayrı raporlanır.
"""

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.cost import TokenUsage, get_token_usage_for_openai
from ragas.metrics import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from backend.config import get_settings
from evaluation.ragas_traces import EXPECTED_EMPTY_TAG

EVALUATOR_LLM_MODEL: str = "gpt-4.1-mini"  # ADR-0009 — runtime adaylarından biri değil


def _build_ragas_dataset(traces: list[dict]) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=t["question"],
            response=t["answer"],
            retrieved_contexts=t["contexts"],
            reference=t["reference"],
        )
        for t in traces
    ]
    # NOT: ragas'ın kendi List[SingleTurnSampleOrMultiTurnSample] parametre
    # tipi invariant, list[SingleTurnSample] runtime'da tamamen geçerli ama
    # statik olarak eşleşmiyor.
    return EvaluationDataset(samples=samples)  # pyright: ignore[reportArgumentType]


def _segment_mean(
    scores: list[float], traces: list[dict]
) -> tuple[float, float | None]:
    """(tüm sorunun ortalaması, expected_empty hariç kalan alt kümenin ortalaması).

    `expected_empty` sorularda context boş olduğu için Context Recall/
    Precision anlamsız kalabilir (bkz. ADR-0009 2026-08-01 güncellemesi) —
    ikinci değer bunları hariç tutar. Hiç `expected_empty` yoksa (küçük bir
    pilot alt kümesinde olabilir) None döner.
    """
    all_mean = sum(scores) / len(scores)
    non_empty = [
        s for s, t in zip(scores, traces) if EXPECTED_EMPTY_TAG not in t["intent_tags"]
    ]
    non_empty_mean = sum(non_empty) / len(non_empty) if non_empty else None
    return all_mean, non_empty_mean


def _build_evaluator_llm() -> ChatOpenAI:
    """Ham bir LangChain ChatOpenAI döner — `ragas.llms.llm_factory()` DEĞİL.

    `llm_factory()`'nin döndürdüğü `InstructorLLM`, ragas 0.3.9'un kendi
    `is_langchain_llm()` sezgiselinde (`hasattr(llm, "agenerate") and not
    hasattr(llm, "run_config")`) yanlışlıkla "LangChain LLM" sanılıyor ve
    metrikler `agenerate_prompt()` (LangChain'e özgü, InstructorLLM'de
    olmayan bir metod) çağırıp çöküyor — gerçek bir pilot çalıştırmasında
    bulundu. Ham `ChatOpenAI` verilince `ragas.evaluation.aevaluate()`'in
    kendi kodu bunu `LangchainLLMWrapper`'a otomatik sarıyor (`run_config`
    ekleniyor), bu da `is_langchain_llm()`'i doğru şekilde False'a düşürüyor.
    """
    # api_key: LangChain SecretStr bekliyor, .get_secret_value() ile açığa
    # çıkarmaya gerek yok — Settings.openai_api_key zaten SecretStr.
    return ChatOpenAI(
        model=EVALUATOR_LLM_MODEL,
        api_key=get_settings().openai_api_key,
    )


def _build_evaluator_embeddings() -> OpenAIEmbeddings:
    """Ham bir LangChain OpenAIEmbeddings döner — aynı gerekçe (`_build_evaluator_llm`)."""
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


def _serialize_token_usage(usage: TokenUsage | list[TokenUsage]) -> list[dict]:
    """`evaluate()`'in döndürdüğü tekil/liste TokenUsage'ı JSON'a yazılabilir hale getirir."""
    if isinstance(usage, list):
        return [u.model_dump() for u in usage]
    return [usage.model_dump()]


def run_ragas_metrics(traces: list[dict]) -> dict:
    """Kayıtlı trace'lerden RAGAS'ın 4 metriğini hesaplar, segmentli özet döner.

    `total_cost()` çağrılmıyor — token başına gerçek fiyatı elle hardcode
    etmek yerine (güncel fiyat değişirse yanıltıcı kalır), sadece gerçek ham
    token sayısı raporlanır; pilot sırasında Eren bunu OpenAI'nin kendi
    dashboard'ıyla karşılaştırır.
    """
    dataset = _build_ragas_dataset(traces)
    metrics = [Faithfulness(), AnswerRelevancy(), ContextPrecision(), ContextRecall()]
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=_build_evaluator_llm(),
        embeddings=_build_evaluator_embeddings(),
        token_usage_parser=get_token_usage_for_openai,
    )
    # NOT: return_executor=False (varsayılan) olduğu için runtime'da her zaman
    # EvaluationResult döner, ama evaluate()'in dönüş tipi statik olarak
    # Union[EvaluationResult, Executor] — Executor'da bu metodlar yok.
    df = result.to_pandas()  # pyright: ignore[reportAttributeAccessIssue]

    metrics_summary: dict[str, dict[str, float | None]] = {}
    for metric_name in ("faithfulness", "answer_relevancy"):
        all_mean, _ = _segment_mean(df[metric_name].tolist(), traces)
        metrics_summary[metric_name] = {"mean_all": all_mean}
    for metric_name in ("context_precision", "context_recall"):
        all_mean, non_empty_mean = _segment_mean(df[metric_name].tolist(), traces)
        metrics_summary[metric_name] = {
            "mean_all": all_mean,
            "mean_excluding_expected_empty": non_empty_mean,
        }

    return {
        "sample_count": len(traces),
        "total_tokens": _serialize_token_usage(
            result.total_tokens()  # pyright: ignore[reportAttributeAccessIssue]
        ),
        "metrics": metrics_summary,
    }

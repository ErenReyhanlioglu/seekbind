"""RAGAS ile RAG pipeline'ının 4 kombinasyonunu değerlendiren script — CLI girişi.

`evaluation/test_set.json`'daki 100 soru, ADR-0023'te kesinleşen 4
kombinasyona (`gpt-4o-mini`/`qwen3:4b-instruct-2507-q4_K_M` ×
`text-embedding-3-small`/`qwen3-embedding:0.6b`) karşı gerçek RAG
pipeline'ından geçirilip RAGAS ile ölçülür. Asıl mantık iki alt modülde:
`evaluation/ragas_traces.py` (pipeline çağrısı, trace toplama) ve
`evaluation/ragas_metrics.py` (RAGAS skor hesaplama) — bu dosya sadece
CLI/orkestrasyon.

Kullanım:
    uv run python -m evaluation.ragas_eval --combo openai-openai --limit 8 --label pilot
    uv run python -m evaluation.ragas_eval --combo all
    uv run python -m evaluation.ragas_eval --from-traces <trace_dosyası.json>
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from backend.services.embedding import (
    EmbeddingProvider,
    OllamaEmbedding,
    OpenAIEmbedding,
)
from backend.services.llm import LLMProvider, OllamaLLM, OpenAILLM
from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.ragas_metrics import run_ragas_metrics
from evaluation.ragas_traces import collect_traces, load_questions, select_subset
from scripts.diagnostics._result_paths import sanitize_model_name

logger = logging.getLogger(__name__)

RESULTS_ROOT: Path = Path("evaluation/results/ragas")
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"  # Windows dosya sisteminde ":" geçersiz

ComboName = Literal["openai-openai", "openai-ollama", "ollama-openai", "ollama-ollama"]
# (LLMProvider sınıfı, EmbeddingProvider sınıfı) — ADR-0023'teki 2×2 ablasyon
# ızgarası. Her sınıf parametresiz kurulur, kendi env değişkeninden
# (OPENAI_LLM_MODEL, OLLAMA_EMBEDDING_MODEL vb.) modelini okur — 4
# kombinasyon zaten bu 4 sınıfın çarpımı, ayrı bir factory gerekmez.
COMBOS: dict[ComboName, tuple[type[LLMProvider], type[EmbeddingProvider]]] = {
    "openai-openai": (OpenAILLM, OpenAIEmbedding),
    "openai-ollama": (OpenAILLM, OllamaEmbedding),
    "ollama-openai": (OllamaLLM, OpenAIEmbedding),
    "ollama-ollama": (OllamaLLM, OllamaEmbedding),
}


def _build_results_dir(llm_model: str, embedder_model: str) -> Path:
    return (
        RESULTS_ROOT
        / sanitize_model_name(llm_model)
        / sanitize_model_name(embedder_model)
    )


def _write_json(
    payload: dict, results_dir: Path, prefix: str, label: str | None
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    filename = (
        f"{prefix}_{label}_{timestamp}.json" if label else f"{prefix}_{timestamp}.json"
    )
    output_path = results_dir / filename
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


async def _run_combo(
    combo_name: ComboName,
    questions: list[dict],
    label: str | None,
    traces_only: bool,
) -> None:
    llm_cls, embedding_cls = COMBOS[combo_name]
    llm_provider = llm_cls()
    embedding_provider = embedding_cls()
    try:
        traces = await collect_traces(llm_provider, embedding_provider, questions)
    finally:
        await llm_provider.close()
        await embedding_provider.close()

    results_dir = _build_results_dir(llm_provider.model, embedding_provider.model)
    traces_path = _write_json({"traces": traces}, results_dir, "traces", label)
    logger.info("Trace'ler kaydedildi: %s", traces_path)

    if traces_only:
        return
    summary = run_ragas_metrics(traces)
    summary["deterministic_metrics"] = compute_deterministic_metrics(traces)
    scores_path = _write_json(summary, results_dir, "scores", label)
    logger.info("RAGAS skorları kaydedildi: %s", scores_path)


async def _run_from_traces(traces_path: Path, label: str | None) -> None:
    payload = json.loads(traces_path.read_text(encoding="utf-8"))
    traces = payload["traces"]
    summary = run_ragas_metrics(traces)
    summary["deterministic_metrics"] = compute_deterministic_metrics(traces)
    scores_path = _write_json(summary, traces_path.parent, "scores", label)
    logger.info("RAGAS skorları kaydedildi: %s", scores_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--combo",
        choices=[*COMBOS.keys(), "all"],
        default="openai-openai",
        help="Hangi LLM×embedding kombinasyonu çalıştırılsın",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Pilot için soru sayısını sınırla"
    )
    parser.add_argument(
        "--label", default=None, help="Sonuç dosyası adına eklenecek etiket"
    )
    parser.add_argument(
        "--traces-only",
        action="store_true",
        help="Sadece pipeline'ı çalıştırıp trace kaydet, RAGAS metriklerini hesaplama",
    )
    parser.add_argument(
        "--from-traces",
        type=Path,
        default=None,
        help="Pipeline'ı atlayıp verilen trace dosyasından RAGAS metriklerini hesapla",
    )
    return parser.parse_args()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = _parse_args()

    if args.from_traces is not None:
        await _run_from_traces(args.from_traces, args.label)
        return

    questions = select_subset(load_questions(), args.limit)
    combo_names: list[ComboName] = (
        list(COMBOS.keys()) if args.combo == "all" else [args.combo]
    )
    for combo_name in combo_names:
        logger.info("Kombinasyon çalıştırılıyor: %s", combo_name)
        await _run_combo(combo_name, questions, args.label, args.traces_only)


if __name__ == "__main__":
    asyncio.run(main())

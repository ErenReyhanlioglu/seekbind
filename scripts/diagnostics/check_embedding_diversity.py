"""Embedding'lerin kategori-içi/kategoriler-arası kosinüs benzerliğini ölçer.

LLM'in ürettiği açıklamaların birbirine çok benzemesi ("mode collapse")
riskini tespit etmek için — bkz. docs/roadmap.md. Birden fazla collection
verilirse (örn. farklı embedding sağlayıcılarının sonuçları, bkz.
feature/fallback-mechanism/Faz 6), her biri ayrı ayrı analiz edilir VE
aralarında bir karşılaştırma raporu üretilir — sonuçları elle diff'lemeye
gerek kalmaz.

Kullanım:
    uv run python -m scripts.diagnostics.check_embedding_diversity
    uv run python -m scripts.diagnostics.check_embedding_diversity --collections businesses_openai businesses_ollama-qwen3-embedding-0-6b
"""

import argparse
import asyncio
import json
import logging
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from qdrant_client import AsyncQdrantClient

from backend.db.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)

DEFAULT_COLLECTIONS: tuple[str, ...] = ("businesses_openai",)
CROSS_CATEGORY_SAMPLE_SIZE: int = 2000
HIGH_SIMILARITY_WARNING_THRESHOLD: float = 0.95
SCROLL_PAGE_SIZE: int = 100
RESULTS_DIR: Path = Path("evaluation/results/diagnostics/embedding_diversity")
# Windows dosya sisteminde ":" geçersiz — smoke_test_search.py ile aynı format.
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"

VectorsByCategory = dict[str, list[np.ndarray]]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """İki vektör arasındaki kosinüs benzerliğini hesaplar (-1 ile 1 arası)."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


async def fetch_vectors_by_category(client: AsyncQdrantClient, collection_name: str) -> VectorsByCategory:
    """Collection'daki tüm noktaları çekip type_normalized'e göre gruplar."""
    grouped: VectorsByCategory = defaultdict(list)
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection_name,
            with_vectors=True,
            with_payload=True,
            limit=SCROLL_PAGE_SIZE,
            offset=offset,
        )
        for point in points:
            # with_payload=True yukarıda her zaman veriliyor, payload hiçbir
            # zaman None olmuyor — Qdrant'ın tip stub'ı bunu genel (with_payload
            # parametresinin değerinden bağımsız) bir Optional olarak işaretliyor.
            category = point.payload["type_normalized"]  # pyright: ignore[reportOptionalSubscript]
            grouped[category].append(np.array(point.vector))
        if offset is None:
            break
    return grouped


def average_within_category_similarity(grouped: VectorsByCategory) -> dict[str, float]:
    """Her kategori için, o kategorideki tüm işletme çiftlerinin ortalama benzerliğini hesaplar."""
    results: dict[str, float] = {}
    for category, vectors in grouped.items():
        if len(vectors) < 2:
            continue
        similarities = [
            cosine_similarity(vectors[i], vectors[j])
            for i in range(len(vectors))
            for j in range(i + 1, len(vectors))
        ]
        results[category] = sum(similarities) / len(similarities)
    return results


def average_cross_category_similarity(grouped: VectorsByCategory, sample_size: int) -> float:
    """Farklı kategorilerden rastgele çiftler örnekleyip ortalama benzerliği hesaplar."""
    categories = [c for c, vectors in grouped.items() if vectors]
    similarities = []
    for _ in range(sample_size):
        category_a, category_b = random.sample(categories, 2)
        vector_a = random.choice(grouped[category_a])
        vector_b = random.choice(grouped[category_b])
        similarities.append(cosine_similarity(vector_a, vector_b))
    return sum(similarities) / len(similarities)


def report(collection_name: str, within: dict[str, float], cross: float) -> None:
    """Tek bir collection'ın sonuçlarını okunabilir şekilde loglar, şüpheli kategorileri işaretler."""
    logger.info("--- %s ---", collection_name)
    logger.info("Kategoriler arası ortalama benzerlik: %.4f", cross)
    logger.info("Kategori-içi ortalama benzerlikler (yüksekten düşüğe):")
    for category, score in sorted(within.items(), key=lambda item: -item[1]):
        warning = " <-- YÜKSEK, incele (mode collapse şüphesi)" if score > HIGH_SIMILARITY_WARNING_THRESHOLD else ""
        logger.info("  %s: %.4f%s", category, score, warning)


def build_result(collection_name: str, within: dict[str, float], cross: float, total_vectors: int) -> dict:
    """Tek bir collection'ın sonuçlarını JSON'a yazılacak yapıya çevirir."""
    flagged = [c for c, score in within.items() if score > HIGH_SIMILARITY_WARNING_THRESHOLD]
    return {
        "collection_name": collection_name,
        "total_categories": len(within),
        "total_vectors": total_vectors,
        "cross_category_average_similarity": round(cross, 4),
        "within_category_average_similarity": {c: round(s, 4) for c, s in within.items()},
        "high_similarity_warning_threshold": HIGH_SIMILARITY_WARNING_THRESHOLD,
        "flagged_categories": flagged,
    }


def build_comparison(results: list[dict]) -> dict:
    """Birden fazla collection'ın sonuçlarını yan yana karşılaştırır — elle
    diff'lemeye gerek kalmadan hangi sağlayıcının hangi kategoride daha
    ayrışık (ya da daha mode-collapse riskli) olduğu tek bakışta görülsün diye."""
    all_categories = sorted({category for r in results for category in r["within_category_average_similarity"]})
    within_by_category = {
        category: {r["collection_name"]: r["within_category_average_similarity"].get(category) for r in results}
        for category in all_categories
    }
    return {
        "collections": [r["collection_name"] for r in results],
        "cross_category_average_similarity_by_collection": {
            r["collection_name"]: r["cross_category_average_similarity"] for r in results
        },
        "within_category_average_similarity_by_category": within_by_category,
    }


def report_comparison(comparison: dict) -> None:
    """Karşılaştırma tablosunu okunabilir şekilde loglar."""
    logger.info("=== KARŞILAŞTIRMA (%s) ===", ", ".join(comparison["collections"]))
    logger.info("Kategoriler arası ortalama benzerlik:")
    for collection_name, cross in comparison["cross_category_average_similarity_by_collection"].items():
        logger.info("  %s: %.4f", collection_name, cross)
    logger.info("Kategori-içi ortalama benzerlik (collection'a göre):")
    for category, by_collection in comparison["within_category_average_similarity_by_category"].items():
        values = "  ".join(
            f"{name}={score:.4f}" if score is not None else f"{name}=—" for name, score in by_collection.items()
        )
        logger.info("  %s: %s", category, values)


def write_output(results: list[dict], comparison: dict | None) -> Path:
    """Tüm collection'ların sonuçlarını (varsa karşılaştırmayla birlikte) TEK
    bir zaman damgalı JSON dosyasına yazar — birden fazla ayrı dosyayı elle
    eşleştirmek yerine tek bir yerden okunabilsin diye."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    suffix = "_".join(r["collection_name"] for r in results) if len(results) == 1 else "comparison"
    output_path = RESULTS_DIR / f"{suffix}_{timestamp}.json"
    payload: dict = {"results": results}
    if comparison is not None:
        payload["comparison"] = comparison
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


async def main(collection_names: tuple[str, ...] = DEFAULT_COLLECTIONS) -> None:
    """Verilen collection'lar için kategori-içi/kategoriler-arası benzerlik
    analizini çalıştırır; birden fazla collection verilirse ayrıca bir
    karşılaştırma raporu üretir."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = get_qdrant_client()
    results: list[dict] = []
    for collection_name in collection_names:
        grouped = await fetch_vectors_by_category(client, collection_name)
        total_vectors = sum(len(v) for v in grouped.values())
        logger.info("'%s': %d kategori, toplam %d vektör okundu", collection_name, len(grouped), total_vectors)

        within = average_within_category_similarity(grouped)
        cross = average_cross_category_similarity(grouped, CROSS_CATEGORY_SAMPLE_SIZE)
        report(collection_name, within, cross)
        results.append(build_result(collection_name, within, cross, total_vectors))

    comparison: dict | None = None
    if len(results) > 1:
        comparison = build_comparison(results)
        report_comparison(comparison)

    output_path = write_output(results, comparison)
    logger.info("Sonuçlar kaydedildi: %s", output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--collections",
        nargs="+",
        default=list(DEFAULT_COLLECTIONS),
        help="Analiz edilecek Qdrant collection adları (birden fazlaysa karşılaştırma raporu da üretilir)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(tuple(args.collections)))

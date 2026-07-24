"""Embedding'lerin kategori-içi/kategoriler-arası kosinüs benzerliğini ölçer.

LLM'in ürettiği açıklamaların birbirine çok benzemesi ("mode collapse")
riskini tespit etmek için — bkz. docs/roadmap.md. Farklı embedding
sağlayıcıları karşılaştırılırken (Faz 6) de aynı script, farklı
collection adıyla tekrar çalıştırılır.
"""

import asyncio
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from qdrant_client import AsyncQdrantClient

from backend.db.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME: str = "businesses_openai"
CROSS_CATEGORY_SAMPLE_SIZE: int = 2000
HIGH_SIMILARITY_WARNING_THRESHOLD: float = 0.95
SCROLL_PAGE_SIZE: int = 100
RESULTS_DIR: Path = Path("evaluation/results/diagnostics")

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
            category = point.payload["type_normalized"]
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


def report(within: dict[str, float], cross: float) -> None:
    """Sonuçları okunabilir şekilde loglar, şüpheli kategorileri işaretler."""
    logger.info("Kategoriler arası ortalama benzerlik: %.4f", cross)
    logger.info("Kategori-içi ortalama benzerlikler (yüksekten düşüğe):")
    for category, score in sorted(within.items(), key=lambda item: -item[1]):
        warning = " <-- YÜKSEK, incele (mode collapse şüphesi)" if score > HIGH_SIMILARITY_WARNING_THRESHOLD else ""
        logger.info("  %s: %.4f%s", category, score, warning)


def build_result(collection_name: str, within: dict[str, float], cross: float, total_vectors: int) -> dict:
    """Sonuçları JSON'a yazılacak yapıya çevirir."""
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


def write_result(result: dict, collection_name: str) -> Path:
    """Sonucu evaluation/results/ altına JSON olarak yazar."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / f"embedding_diversity_{collection_name}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


async def main(collection_name: str = DEFAULT_COLLECTION_NAME) -> None:
    """Verilen collection için kategori-içi/kategoriler-arası benzerlik analizini çalıştırır."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = get_qdrant_client()
    grouped = await fetch_vectors_by_category(client, collection_name)
    total_vectors = sum(len(v) for v in grouped.values())
    logger.info("'%s': %d kategori, toplam %d vektör okundu", collection_name, len(grouped), total_vectors)

    within = average_within_category_similarity(grouped)
    cross = average_cross_category_similarity(grouped, CROSS_CATEGORY_SAMPLE_SIZE)
    report(within, cross)

    result = build_result(collection_name, within, cross, total_vectors)
    output_path = write_result(result, collection_name)
    logger.info("Sonuçlar kaydedildi: %s", output_path)


if __name__ == "__main__":
    collection_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COLLECTION_NAME
    asyncio.run(main(collection_arg))

"""#2 raporu: tüm kategorilerde "cheap"/"expensive" fiyat katmanlarının sağlığını tarar (ADR-0027).

Bilinen referans değerler: 27 kategoriden 24'ü sağlıklı (~%25 kapsam,
persentil tanımı gereği beklenen), 3'ü (Göz Doktoru, Cilt Bakım Merkezi,
Noter) simetrik MIN_COUNT'un altında.

Kullanım:
    uv run python -m scripts.ragas_testset.scan_price_distinctiveness
"""

import asyncio

from backend.db.session import get_session_factory
from scripts.constants import QUERY_TERM_TO_TYPE
from scripts.ragas_testset import price_distinctiveness
from scripts.ragas_testset.coverage_stats import SplitResult
from scripts.ragas_testset.reports import write_report


async def main() -> None:
    categories = sorted(set(QUERY_TERM_TO_TYPE.values()))
    results: dict[str, dict[str, SplitResult]] = {}

    session_factory = get_session_factory()
    async with session_factory() as session:
        for category in categories:
            cheap = await price_distinctiveness.check_category(
                session, category, "cheap"
            )
            expensive = await price_distinctiveness.check_category(
                session, category, "expensive"
            )
            results[category] = {"cheap": cheap, "expensive": expensive}

    report = {
        category: {tier: split.model_dump(mode="json") for tier, split in tiers.items()}
        for category, tiers in results.items()
    }
    path = write_report("price_distinctiveness", report)

    degenerate = [
        category
        for category, tiers in results.items()
        if not tiers["cheap"].is_viable or not tiers["expensive"].is_viable
    ]
    print(
        f"{len(categories)} kategori tarandı, {len(degenerate)} tanesi dejenere: {degenerate}"
    )
    print(f"Rapor: {path}")


if __name__ == "__main__":
    asyncio.run(main())

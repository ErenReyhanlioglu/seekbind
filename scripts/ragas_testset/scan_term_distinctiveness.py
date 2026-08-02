"""#1 raporu: tüm kategorilerin ayırt edici servis terimlerini tarar (ADR-0027).

Bilinen referans değerler: Fizyoterapist'te "fıtık" en üstte (H=1.000,
10/20), Berber'de "sakal" hiç listede yok (neredeyse evrensel, H≈0).

Kullanım:
    uv run python -m scripts.ragas_testset.scan_term_distinctiveness
"""

import asyncio

from backend.db.session import get_session_factory
from scripts.constants import QUERY_TERM_TO_TYPE
from scripts.ragas_testset import term_distinctiveness
from scripts.ragas_testset.reports import write_report


async def main() -> None:
    categories = sorted(set(QUERY_TERM_TO_TYPE.values()))
    report: dict[str, list[dict[str, object]]] = {}

    session_factory = get_session_factory()
    async with session_factory() as session:
        for category in categories:
            candidates = await term_distinctiveness.scan_category(session, category)
            report[category] = [
                candidate.model_dump(mode="json") for candidate in candidates
            ]

    path = write_report("term_distinctiveness", report)
    total_candidates = sum(len(candidates) for candidates in report.values())
    print(
        f"{len(categories)} kategori tarandı, toplam {total_candidates} ayırt edici terim bulundu."
    )
    print(f"Rapor: {path}")


if __name__ == "__main__":
    asyncio.run(main())

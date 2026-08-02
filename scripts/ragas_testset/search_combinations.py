"""#4 raporu: Apriori-tarzı çok-yüklemli kombinasyon araması (ADR-0027).

Bilinen referans değer: Fizyoterapist'te ~26 geçerli kombinasyon
(kanonik sıra + "boş yüklem" düzeltmesinden önce sahte 110 çıkmıştı).
Mevcut `test_set.json` sorularıyla çakışan kombinasyonlar rapora hiç
girmiyor (bkz. `existing_coverage.py`).

Kullanım:
    uv run python -m scripts.ragas_testset.search_combinations
    uv run python -m scripts.ragas_testset.search_combinations --category Fizyoterapist
"""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_session_factory
from scripts.constants import QUERY_TERM_TO_TYPE
from scripts.ragas_testset import combination_search, term_distinctiveness
from scripts.ragas_testset.business_lookup import fetch_category_businesses
from scripts.ragas_testset.existing_coverage import (
    PredicateSlot,
    is_duplicate,
    load_existing_predicate_sets,
)
from scripts.ragas_testset.predicates import build_predicate_groups
from scripts.ragas_testset.reports import write_report

TEST_SET_PATH: Path = Path("evaluation/test_set.json")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Çok-yüklemli kombinasyon araması çalıştırır."
    )
    parser.add_argument(
        "--category", help="Sadece bu kategoriyi tara (verilmezse tüm kategoriler)."
    )
    return parser.parse_args()


async def _search_one_category(
    session: AsyncSession,
    category: str,
    existing_by_category: dict[str, set[frozenset[PredicateSlot]]],
) -> list[combination_search.ViableCombination]:
    businesses = await fetch_category_businesses(session, category)
    term_candidates = await term_distinctiveness.scan_category(session, category)
    predicate_groups = await build_predicate_groups(
        session, category, businesses, term_candidates
    )
    all_ids = frozenset(business.id for business in businesses)
    combinations = combination_search.search(predicate_groups, all_ids)

    existing = existing_by_category.get(category, set())
    return [c for c in combinations if not is_duplicate(c, existing)]


async def main() -> None:
    args = _parse_args()
    categories = (
        [args.category] if args.category else sorted(set(QUERY_TERM_TO_TYPE.values()))
    )
    existing_by_category = load_existing_predicate_sets(TEST_SET_PATH)

    report: dict[str, list[dict[str, object]]] = {}
    session_factory = get_session_factory()
    async with session_factory() as session:
        for category in categories:
            combinations = await _search_one_category(
                session, category, existing_by_category
            )
            report[category] = [c.model_dump(mode="json") for c in combinations]

    path = write_report("combination_search", report)
    total = sum(len(combinations) for combinations in report.values())
    print(
        f"{len(categories)} kategori tarandı, toplam {total} yeni "
        "(mevcut sorularla çakışmayan) kombinasyon bulundu."
    )
    print(f"Rapor: {path}")


if __name__ == "__main__":
    asyncio.run(main())

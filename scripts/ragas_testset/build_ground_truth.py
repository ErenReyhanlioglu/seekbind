"""`evaluation/test_set.json`'un `expected_business_ids`'ini hesaplayan CLI.

Eski `scripts/build_ragas_ground_truth.py`'nin yerini alır (bkz.
ADR-0027) — mantığı `ground_truth_filters.py`/`ground_truth_resolvers.py`'ye
taşındı, artık `service_keyword` sert filtresini de (problem #1) destekliyor.

Her soru için "doğru" işletme kümesi, RAG pipeline'ındaki LLM'e (intent
parsing) hiç dokunmadan, doğrudan gerçek DB verisinden hesaplanır — amaç,
ground truth'un test edilen sistemden bağımsız/objektif kalması (bkz.
ADR-0009'daki evaluator bağımsızlığı gerekçesiyle aynı ilke).

ÖNEMLİ KISIT: gün/saat bazlı sorular (`day_of_week`/`time_of_day`) canlı
`appointment_slots` tablosuna DEĞİL, işletmenin haftalık `working_hours`
programına bakar (bkz. `ground_truth_filters.schedule_matches`) — bu test
seti sabit kalıp haftalar/aylar sonra tekrar tekrar çalıştırılacağı için,
o an "bugün"e göre üretilmiş somut slot satırlarına bağlı bir ground
truth her çalıştırmada sessizce bozulurdu.

Kullanım:
    uv run python -m scripts.ragas_testset.build_ground_truth
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from backend.db.session import get_session_factory
from scripts.ragas_testset.ground_truth_resolvers import compute_expected_ids
from scripts.ragas_testset.reports import write_report

TEST_SET_PATH: Path = Path("evaluation/test_set.json")


async def _fetch_details(
    session: AsyncSession, business_ids: list[int]
) -> list[dict[str, object]]:
    """Referans metni yazarken kullanılacak gerçek işletme alanlarını döner."""
    if not business_ids:
        return []
    result = await session.execute(
        select(Business).where(Business.id.in_(business_ids))
    )
    return [
        {
            "id": business.id,
            "title": business.title,
            "type_normalized": business.type_normalized,
            "price_min": business.price_min,
            "price_max": business.price_max,
            "weighted_rating": business.weighted_rating,
            "gender": business.gender,
            "online_available": business.online_available,
            "services": business.services,
            "address": business.address,
            "rich_description": business.rich_description,
        }
        for business in result.scalars().all()
    ]


async def main() -> None:
    questions = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    details: dict[str, list[dict[str, object]]] = {}

    session_factory = get_session_factory()
    async with session_factory() as session:
        for question in questions:
            expected_ids = await compute_expected_ids(session, question)
            question["expected_business_ids"] = expected_ids
            details[question["id"]] = await _fetch_details(session, expected_ids)

    TEST_SET_PATH.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    details_path = write_report("ground_truth_details", details)

    empty_count = sum(
        1 for question in questions if not question["expected_business_ids"]
    )
    print(f"{len(questions)} soru işlendi, {empty_count} tanesi boş küme döndürdü.")
    print(f"İşletme detayları: {details_path}")


if __name__ == "__main__":
    asyncio.run(main())

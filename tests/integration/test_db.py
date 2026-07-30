"""DB katmanının, N+1 dışındaki CLAUDE.md standartlarına uygunluğunu
doğrudan doğrulayan entegrasyon testleri: transaction rollback ve index
kullanımı.

N+1 regresyon testleri bilerek burada DEĞİL — bkz. `test_db_query_counts.py`
(farklı bir ölçüm yöntemi, karşılaştırmalı sorgu sayısı).
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import AppointmentSlot, UserProfile
from backend.db.session import get_db_session, get_session_factory

pytestmark = pytest.mark.integration


class _SimulatedRouteFailure(Exception):
    """`get_db_session`'ın rollback yolunu tetiklemek için kullanılan,
    testin kendi ürettiği hata — gerçek bir route hatasını simüle eder."""


async def test_get_db_session_rolls_back_on_exception() -> None:
    """`get_db_session` (backend/db/session.py), `yield` sonrası bir istisna
    fırlatıldığında gerçekten `rollback()` çağırıyor mu — `savepoint_session`'a
    hiç dokunmadan, fonksiyonun kendisini gerçek bir async generator olarak
    çalıştırarak kanıtlar. SAVEPOINT deseni bilerek devre dışı: test ettiğimiz
    şey tam olarak bu commit/rollback sarmalayıcısının kendisi, onu SAVEPOINT'in
    arkasına saklarsak asıl davranışı değil SAVEPOINT'in davranışını test
    etmiş oluruz.
    """
    marker_name = f"rollback-test-{uuid4()}"

    try:
        generator = get_db_session()
        session = await generator.__anext__()
        session.add(UserProfile(name=marker_name))
        await session.flush()

        with pytest.raises(_SimulatedRouteFailure):
            await generator.athrow(_SimulatedRouteFailure("simüle edilmiş route hatası"))

        async with get_session_factory()() as fresh_session:
            leftover = (
                await fresh_session.execute(select(UserProfile).where(UserProfile.name == marker_name))
            ).scalar_one_or_none()
        assert leftover is None
    finally:
        # Savunma amaçlı: rollback beklenildiği gibi çalışmasa bile dev DB'de iz kalmasın.
        async with get_session_factory()() as cleanup_session:
            await cleanup_session.execute(delete(UserProfile).where(UserProfile.name == marker_name))
            await cleanup_session.commit()


async def test_appointment_slot_composite_index_is_used(savepoint_session: AsyncSession) -> None:
    """`fetch_available_business_ids()`'in (search/availability.py) ürettiği
    sorgu paterni, gerçekten `ix_slots_business_start_booked` bileşik
    index'ini kullanıyor mu — Seq Scan'e düşmüyor mu, gerçek dev veriye
    (32k+ satır) karşı `EXPLAIN` ile doğrulanır (bkz. `docs/database_schema.md`
    "İndexlenen kolonlar").
    """
    business_ids = list(range(1, 31))
    stmt = (
        select(AppointmentSlot.business_id)
        .where(
            AppointmentSlot.business_id.in_(business_ids),
            AppointmentSlot.start_time >= datetime(2020, 1, 1),
            AppointmentSlot.start_time < datetime(2030, 1, 1),
            AppointmentSlot.is_booked.is_(False),
        )
        .distinct()
    )
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    result = await savepoint_session.execute(text(f"EXPLAIN (FORMAT JSON) {compiled}"))
    plan = result.scalar_one()
    plan_text = str(plan)

    assert "Seq Scan" not in plan_text
    assert "ix_slots_business_start_booked" in plan_text

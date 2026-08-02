"""Kategori bazlı işletme sorgusu — pakette birden fazla modülde tekrar eden ortak yardımcı."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business


async def fetch_category_businesses(
    session: AsyncSession, category: str
) -> list[Business]:
    """Bir kategorideki tüm işletmeleri döner."""
    result = await session.execute(
        select(Business).where(Business.type_normalized == category)
    )
    return list(result.scalars().all())

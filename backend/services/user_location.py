"""Kullanıcının referans konumunu (UserProfile.latitude/longitude) çözer.

Gerçek bir auth/oturum sistemi olmadığı için (bkz. `UserProfile` docstring'i)
konum kaynağı basit: kullanıcının profilindeki lat/lon. `/recommend`'in
`near_me` intent sinyali ve calendar-service'in `near_me` parametresi aynı
bu fonksiyonu kullanır — konum çözme mantığı iki yerde ayrı ayrı yazılmaz.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import UserProfile

logger = logging.getLogger(__name__)


async def get_user_reference_location(
    session: AsyncSession, user_id: int
) -> tuple[float, float] | None:
    """Kullanıcının `UserProfile`'daki (latitude, longitude) çiftini döner.

    Profil yoksa ya da konum NULL ise sessizce None döner — çağıran bunu
    "mesafe sinyali uygulanamadı" olarak yorumlar, arama/rezervasyon
    çökmez.
    """
    user = (
        await session.execute(select(UserProfile).where(UserProfile.id == user_id))
    ).scalar_one_or_none()
    if user is None or user.latitude is None or user.longitude is None:
        logger.warning("user_id=%s için referans konum bulunamadı", user_id)
        return None
    return user.latitude, user.longitude

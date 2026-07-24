"""Async SQLAlchemy engine ve session yönetimi.

Engine ve session factory, config.py'deki get_settings() ile aynı
desende (lru_cache ile önbelleklenmiş fabrika fonksiyonu) tanımlanır.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """Async Postgres engine'ini önbellekten döner, tekrar oluşturmaz."""
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=settings.debug)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory'yi önbellekten döner."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency injection için async DB session üretir.

    İstek başarıyla biterse commit edilir; bir hata oluşursa rollback
    yapılıp hata tekrar fırlatılır (route handler'ların her yerde
    manuel commit çağırmasına gerek kalmaz).
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

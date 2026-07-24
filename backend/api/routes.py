"""API endpoint tanımları."""

from functools import lru_cache

from fastapi import APIRouter, Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import DependencyStatus, HealthCheckResponse
from backend.config import get_settings
from backend.db.session import get_db_session

router = APIRouter()


@lru_cache
def get_qdrant_client() -> AsyncQdrantClient:
    """Qdrant client'ını önbellekten döner, tekrar oluşturmaz."""
    settings = get_settings()
    return AsyncQdrantClient(url=settings.qdrant_url)


async def check_postgres(session: AsyncSession) -> DependencyStatus:
    """Postgres'e gerçek bir sorgu atıp ulaşılabilir mi diye kontrol eder."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        # Bilerek genel Exception: hata tipi ne olursa olsun (SQLAlchemy,
        # asyncio/socket katmanı vb.) tepkimiz aynı — "unhealthy" işaretle,
        # detayını raporla. Daraltırsak health-check kendisi 500 ile çöker.
        return DependencyStatus(name="postgres", healthy=False, detail=str(e))
    return DependencyStatus(name="postgres", healthy=True)


async def check_qdrant(client: AsyncQdrantClient) -> DependencyStatus:
    """Qdrant'a gerçek bir istek atıp ulaşılabilir mi diye kontrol eder."""
    try:
        await client.get_collections()
    except Exception as e:
        # bkz. check_postgres'teki not — aynı gerekçe burada da geçerli
        return DependencyStatus(name="qdrant", healthy=False, detail=str(e))
    return DependencyStatus(name="qdrant", healthy=True)


def check_llm_config() -> DependencyStatus:
    """LLM için gerçek bir çağrı atmaz (ücretli), sadece API key tanımlı mı bakar."""
    settings = get_settings()
    configured = bool(settings.openai_api_key.get_secret_value())
    detail = None if configured else "OPENAI_API_KEY tanımlı değil"
    return DependencyStatus(name="llm_config", healthy=configured, detail=detail)


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    session: AsyncSession = Depends(get_db_session),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> HealthCheckResponse:
    """Derin health-check: Postgres ve Qdrant'a gerçekten ulaşılabiliyor mu kontrol eder."""
    dependencies = [
        await check_postgres(session),
        await check_qdrant(qdrant_client),
        check_llm_config(),
    ]
    status = "healthy" if all(dep.healthy for dep in dependencies) else "unhealthy"
    return HealthCheckResponse(status=status, dependencies=dependencies)

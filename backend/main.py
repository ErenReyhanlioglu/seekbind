"""FastAPI uygulamasının giriş noktası."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from backend.api.routes import router
from backend.config import get_settings
from backend.core.monitoring import get_langfuse_client
from backend.db.qdrant import get_qdrant_client
from backend.db.redis import get_redis_client
from backend.db.session import get_engine, get_session_factory
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.services.embedding import get_embedding_provider
from backend.services.llm import get_llm_provider
from backend.services.search import get_bm25_index, get_reranker_provider, periodic_refresh_loop


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Başlangıçta BM25 index'i kurar ve periyodik yenileme görevini başlatır;
    kapanışta bu görevi + DB engine'i + Qdrant/Redis client'larını düzgün kapatır.

    İlk kurulum burada try/except'siz — DB'ye ulaşılamıyorsa uygulama fail-fast
    çökmeli (sessizce boş bir index'le ayağa kalkmak yerine). Periyodik
    yenilemedeki geçici hata toleransı periodic_refresh_loop'un kendi işi.
    """
    settings = get_settings()
    bm25_index = get_bm25_index()
    async with get_session_factory()() as session:
        await bm25_index.refresh_if_stale(session)

    refresh_task = asyncio.create_task(
        periodic_refresh_loop(bm25_index, get_session_factory(), settings.bm25_refresh_interval_seconds)
    )

    yield

    refresh_task.cancel()
    with suppress(asyncio.CancelledError):
        await refresh_task

    await get_engine().dispose()
    await get_qdrant_client().close()
    await get_redis_client().aclose()
    await get_reranker_provider().close()
    await get_llm_provider().close()
    await get_embedding_provider().close()
    get_langfuse_client().flush()


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluşturur."""
    app = FastAPI(title="SeekBind API", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(RateLimitMiddleware)  # GZip'ten SONRA — en dışta, isteği ilk karşılayan
    app.include_router(router)
    return app


app = create_app()

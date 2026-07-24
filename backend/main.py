"""FastAPI uygulamasının giriş noktası."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from backend.api.routes import get_qdrant_client, router
from backend.db.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Kapanışta DB engine'i ve Qdrant client'ını düzgün kapatır (graceful shutdown)."""
    yield
    await get_engine().dispose()
    await get_qdrant_client().close()


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluşturur."""
    app = FastAPI(title="SeekBind API", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.include_router(router)
    return app


app = create_app()

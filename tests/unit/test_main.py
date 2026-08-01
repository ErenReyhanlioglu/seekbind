"""backend/main.py için birim testler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

import backend.main as main_module
from backend.main import create_app, lifespan
from backend.middleware.rate_limit import RateLimitMiddleware


class _FakeSessionContextManager:
    """`get_session_factory()()`'ın döndürdüğü async context manager'ı taklit eder."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def test_create_app_returns_fastapi_instance_with_router_included() -> None:
    """Route'ların varlığını `app.routes`'tan değil `openapi()` şemasından
    kontrol ediyoruz — FastAPI'nin include_router() sonrası iç route temsili
    sürüm bazlı değişebiliyor, openapi() şeması kararlı bir public API."""
    app = create_app()

    assert isinstance(app, FastAPI)
    paths = set(app.openapi()["paths"].keys())
    assert "/health" in paths
    assert "/recommend" in paths


def test_create_app_adds_gzip_middleware() -> None:
    app = create_app()

    middleware_classes = [middleware.cls for middleware in app.user_middleware]
    assert GZipMiddleware in middleware_classes


def test_create_app_adds_rate_limit_middleware_before_gzip() -> None:
    """`app.user_middleware`'de son eklenen en başta durur (Starlette LIFO
    sarmalama sırası) — `RateLimitMiddleware` GZip'ten SONRA eklendiği için
    listede GZip'ten önceki indekste olmalı, isteği ilk o karşılasın diye
    (GZip'in hiç çalışması gerekmesin rate limit reddederken)."""
    app = create_app()

    middleware_classes: list[object] = [
        middleware.cls for middleware in app.user_middleware
    ]
    assert RateLimitMiddleware in middleware_classes
    assert middleware_classes.index(RateLimitMiddleware) < middleware_classes.index(
        GZipMiddleware
    )


def _patch_lifespan_dependencies(
    monkeypatch, fake_session: AsyncMock
) -> dict[str, MagicMock]:
    """lifespan()'ın kapanışta kapattığı 4 kaynağı + BM25/langfuse'u fake'ler,
    gerçek DB/Qdrant/LLM/Langfuse'a hiç dokunmadan test edilebilsin diye."""
    fake_bm25_index = MagicMock(refresh_if_stale=AsyncMock())
    fake_engine = MagicMock(dispose=AsyncMock())
    fake_qdrant_client = MagicMock(close=AsyncMock())
    fake_reranker_provider = MagicMock(close=AsyncMock())
    fake_llm_provider = MagicMock(close=AsyncMock())
    fake_langfuse_client = MagicMock(flush=MagicMock())

    async def fake_periodic_refresh_loop(*args: object, **kwargs: object) -> None:
        # Gerçek periodic_refresh_loop hiç dönmez (sonsuz döngü) — burada da
        # aynı davranışı taklit ediyoruz, shutdown'da gerçekten cancel
        # edildiğini test edebilmek için sonsuza kadar bekleyen bir coroutine.
        await asyncio.Event().wait()

    monkeypatch.setattr(
        main_module,
        "get_settings",
        lambda: MagicMock(bm25_refresh_interval_seconds=300),
    )
    monkeypatch.setattr(main_module, "get_bm25_index", lambda: fake_bm25_index)
    monkeypatch.setattr(
        main_module,
        "get_session_factory",
        lambda: (lambda: _FakeSessionContextManager(fake_session)),
    )
    monkeypatch.setattr(
        main_module, "periodic_refresh_loop", fake_periodic_refresh_loop
    )
    monkeypatch.setattr(main_module, "get_engine", lambda: fake_engine)
    monkeypatch.setattr(main_module, "get_qdrant_client", lambda: fake_qdrant_client)
    monkeypatch.setattr(
        main_module, "get_reranker_provider", lambda: fake_reranker_provider
    )
    monkeypatch.setattr(main_module, "get_llm_provider", lambda: fake_llm_provider)
    monkeypatch.setattr(
        main_module, "get_langfuse_client", lambda: fake_langfuse_client
    )

    return {
        "bm25_index": fake_bm25_index,
        "engine": fake_engine,
        "qdrant_client": fake_qdrant_client,
        "reranker_provider": fake_reranker_provider,
        "llm_provider": fake_llm_provider,
        "langfuse_client": fake_langfuse_client,
    }


async def test_lifespan_refreshes_bm25_index_on_startup(monkeypatch) -> None:
    fake_session = AsyncMock()
    fakes = _patch_lifespan_dependencies(monkeypatch, fake_session)

    async with lifespan(MagicMock()):
        pass

    fakes["bm25_index"].refresh_if_stale.assert_awaited_once_with(fake_session)


async def test_lifespan_closes_all_resources_on_shutdown(monkeypatch) -> None:
    """CLAUDE.md: shutdown'da DB engine, HTTP client oturumları ve bekleyen
    arka plan görevleri düzgün kapatılmalı — açık kalan bağlantılar veri
    kaybına yol açabilir."""
    fake_session = AsyncMock()
    fakes = _patch_lifespan_dependencies(monkeypatch, fake_session)

    async with lifespan(MagicMock()):
        pass

    fakes["engine"].dispose.assert_awaited_once()
    fakes["qdrant_client"].close.assert_awaited_once()
    fakes["reranker_provider"].close.assert_awaited_once()
    fakes["llm_provider"].close.assert_awaited_once()
    fakes["langfuse_client"].flush.assert_called_once()


async def test_lifespan_cancels_periodic_refresh_task_on_shutdown(monkeypatch) -> None:
    """periodic_refresh_loop sonsuz döngü olduğu için, shutdown'da gerçekten
    iptal edilmezse süreç asla kapanmaz (asyncio.CancelledError bastırılmalı,
    dışarı sızmamalı)."""
    fake_session = AsyncMock()
    _patch_lifespan_dependencies(monkeypatch, fake_session)

    async with lifespan(MagicMock()):
        pass
    # `lifespan` bloğu hatasız tamamlandıysa, sonsuz döngüdeki refresh_task
    # gerçekten cancel edilmiş ve CancelledError düzgün bastırılmış demektir
    # — aksi halde bu test asla bitmez (asyncio.Event().wait() sonsuza kadar
    # bekler) ya da CancelledError dışarı sızardı.

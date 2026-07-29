"""backend/db/session.py için birim testler."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.db.session as session_module
from backend.db.session import get_db_session, get_engine, get_session_factory


class _FakeSessionContextManager:
    """`async_sessionmaker()()`'ın döndürdüğü async context manager'ı taklit eder."""

    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def test_get_engine_uses_database_url_and_debug_from_settings(monkeypatch) -> None:
    get_engine.cache_clear()
    fake_settings = MagicMock(database_url="postgresql+asyncpg://test", debug=True)
    monkeypatch.setattr(session_module, "get_settings", lambda: fake_settings)
    fake_engine = MagicMock()
    fake_create_engine = MagicMock(return_value=fake_engine)
    monkeypatch.setattr(session_module, "create_async_engine", fake_create_engine)

    try:
        engine = get_engine()

        assert engine is fake_engine
        fake_create_engine.assert_called_once_with("postgresql+asyncpg://test", echo=True)
    finally:
        get_engine.cache_clear()


def test_get_engine_returns_same_instance_on_repeated_calls(monkeypatch) -> None:
    get_engine.cache_clear()
    monkeypatch.setattr(session_module, "get_settings", lambda: MagicMock(database_url="x", debug=False))
    monkeypatch.setattr(session_module, "create_async_engine", MagicMock(side_effect=lambda *a, **k: MagicMock()))

    try:
        assert get_engine() is get_engine()
    finally:
        get_engine.cache_clear()


def test_get_session_factory_uses_engine_and_expire_on_commit_false(monkeypatch) -> None:
    get_session_factory.cache_clear()
    fake_engine = MagicMock()
    monkeypatch.setattr(session_module, "get_engine", lambda: fake_engine)
    fake_factory = MagicMock()
    fake_async_sessionmaker = MagicMock(return_value=fake_factory)
    monkeypatch.setattr(session_module, "async_sessionmaker", fake_async_sessionmaker)

    try:
        factory = get_session_factory()

        assert factory is fake_factory
        fake_async_sessionmaker.assert_called_once_with(fake_engine, expire_on_commit=False)
    finally:
        get_session_factory.cache_clear()


def test_get_session_factory_returns_same_instance_on_repeated_calls(monkeypatch) -> None:
    get_session_factory.cache_clear()
    monkeypatch.setattr(session_module, "get_engine", lambda: MagicMock())
    monkeypatch.setattr(session_module, "async_sessionmaker", MagicMock(side_effect=lambda *a, **k: MagicMock()))

    try:
        assert get_session_factory() is get_session_factory()
    finally:
        get_session_factory.cache_clear()


async def test_get_db_session_commits_on_success(monkeypatch) -> None:
    fake_session = AsyncMock()
    monkeypatch.setattr(
        session_module, "get_session_factory", lambda: (lambda: _FakeSessionContextManager(fake_session))
    )

    async for session in get_db_session():
        assert session is fake_session

    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_called()


async def test_get_db_session_rolls_back_and_reraises_on_exception(monkeypatch) -> None:
    """Route handler ya da başka bir dependency hata fırlatırsa, session
    commit edilmemeli, rollback yapılıp hata olduğu gibi yeniden fırlatılmalı
    (bkz. get_db_session'ın docstring'i)."""
    fake_session = AsyncMock()
    monkeypatch.setattr(
        session_module, "get_session_factory", lambda: (lambda: _FakeSessionContextManager(fake_session))
    )

    generator = get_db_session()
    session = await generator.__anext__()
    assert session is fake_session

    with pytest.raises(ValueError):
        await generator.athrow(ValueError("boom"))

    fake_session.rollback.assert_awaited_once()
    fake_session.commit.assert_not_called()

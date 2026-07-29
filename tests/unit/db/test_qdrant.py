"""backend/db/qdrant.py için birim testler."""

from unittest.mock import MagicMock

import backend.db.qdrant as qdrant_module
from backend.db.qdrant import get_qdrant_client


def test_get_qdrant_client_uses_qdrant_url_from_settings(monkeypatch) -> None:
    get_qdrant_client.cache_clear()
    fake_settings = MagicMock(qdrant_url="http://test-qdrant:6333")
    monkeypatch.setattr(qdrant_module, "get_settings", lambda: fake_settings)
    fake_client = MagicMock()
    fake_constructor = MagicMock(return_value=fake_client)
    monkeypatch.setattr(qdrant_module, "AsyncQdrantClient", fake_constructor)

    try:
        client = get_qdrant_client()

        assert client is fake_client
        fake_constructor.assert_called_once_with(url="http://test-qdrant:6333")
    finally:
        get_qdrant_client.cache_clear()


def test_get_qdrant_client_returns_same_instance_on_repeated_calls(monkeypatch) -> None:
    """lru_cache singleton davranışı — pahalı client'lar her istekte
    yeniden oluşturulmamalı (bkz. CLAUDE.md)."""
    get_qdrant_client.cache_clear()
    monkeypatch.setattr(qdrant_module, "get_settings", lambda: MagicMock(qdrant_url="http://test-qdrant:6333"))
    monkeypatch.setattr(qdrant_module, "AsyncQdrantClient", MagicMock(side_effect=lambda **kwargs: MagicMock()))

    try:
        first = get_qdrant_client()
        second = get_qdrant_client()

        assert first is second
    finally:
        get_qdrant_client.cache_clear()

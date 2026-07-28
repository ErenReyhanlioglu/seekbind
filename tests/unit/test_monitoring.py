"""backend/core/monitoring.py için birim testler."""

import os

import pytest
from langfuse import Langfuse  # pyright: ignore[reportPrivateImportUsage]  # bkz. backend/core/monitoring.py

from backend.core.monitoring import get_langfuse_client


def test_get_langfuse_client_returns_langfuse_instance() -> None:
    get_langfuse_client.cache_clear()

    try:
        client = get_langfuse_client()
        assert isinstance(client, Langfuse)
    finally:
        get_langfuse_client.cache_clear()


def test_get_langfuse_client_sets_environment_variables_for_openai_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """`langfuse.openai.AsyncOpenAI` sarmalayıcısı kendi iç singleton'ında
    sadece `os.environ`'a bakıyor (bkz. monitoring.py docstring) — bu testin
    varlık nedeni tam olarak bu: değerler os.environ'a da yazılmazsa
    izleme sessizce devre dışı kalıyor, bunu gerçek bir çağrıda bulduk."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    get_langfuse_client.cache_clear()

    try:
        get_langfuse_client()
        assert os.environ["LANGFUSE_PUBLIC_KEY"] != ""
        assert os.environ["LANGFUSE_SECRET_KEY"] != ""
        assert os.environ["LANGFUSE_HOST"] != ""
    finally:
        get_langfuse_client.cache_clear()

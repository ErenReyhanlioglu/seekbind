"""backend/services/rag/pricing.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.rag.pricing import resolve_price_threshold


def _session_returning(value: float | None) -> AsyncMock:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalar=lambda: value)
    return session


async def test_resolve_price_threshold_returns_none_none_when_category_missing() -> None:
    session = AsyncMock()

    min_price, max_price = await resolve_price_threshold(session, None, "cheap")

    assert (min_price, max_price) == (None, None)
    session.execute.assert_not_called()


async def test_resolve_price_threshold_returns_none_none_when_preference_missing() -> None:
    session = AsyncMock()

    min_price, max_price = await resolve_price_threshold(session, "Diş Kliniği", None)

    assert (min_price, max_price) == (None, None)
    session.execute.assert_not_called()


async def test_resolve_price_threshold_returns_max_price_for_cheap_preference() -> None:
    session = _session_returning(950.0)

    min_price, max_price = await resolve_price_threshold(session, "Diş Kliniği", "cheap")

    assert min_price is None
    assert max_price == 950


async def test_resolve_price_threshold_cheap_queries_price_min_column() -> None:
    """"cheap" eşiği, price_min <= max_price şeklinde uygulanıyor
    (filters.py'deki overlap mantığı) — yani percentile de price_min
    kolonundan hesaplanmalı, price_max'tan DEĞİL. İlk implementasyonda
    tam olarak bu ters karıştırılmıştı (gerçek DB'de doğrulandı: bir
    kategoride price_min'in 25. percentile'ı 2174 TL iken price_max'ınki
    5735 TL çıktı — yanlış alan kullanılırsa eşik anlamsız yükseliyor).
    Bu test, mock'un dönen SAYIYI değil, GERÇEKTEN SORGULANAN KOLONU
    kontrol ediyor — önceki testler bunu kontrol etmediği için hata
    gerçek bir LLM smoke test'inde ortaya çıkana kadar fark edilmedi.
    """
    session = _session_returning(2174.0)

    await resolve_price_threshold(session, "Diş Kliniği", "cheap")

    executed_statement = str(session.execute.call_args.args[0])
    assert "price_min" in executed_statement
    assert "price_max" not in executed_statement


async def test_resolve_price_threshold_returns_min_price_for_expensive_preference() -> None:
    session = _session_returning(12000.0)

    min_price, max_price = await resolve_price_threshold(session, "Avukat", "expensive")

    assert min_price == 12000
    assert max_price is None


async def test_resolve_price_threshold_expensive_queries_price_max_column() -> None:
    """"expensive" eşiği price_max >= min_price şeklinde uygulanıyor —
    percentile price_max kolonundan hesaplanmalı, price_min'den değil
    (bkz. test_resolve_price_threshold_cheap_queries_price_min_column)."""
    session = _session_returning(15000.0)

    await resolve_price_threshold(session, "Avukat", "expensive")

    executed_statement = str(session.execute.call_args.args[0])
    assert "price_max" in executed_statement
    assert "price_min" not in executed_statement


async def test_resolve_price_threshold_returns_none_when_category_has_no_businesses() -> None:
    """percentile_cont, hiç satır yoksa NULL/None döner — bu durumda da
    filtre uygulanmamalı, hata fırlatılmamalı."""
    session = _session_returning(None)

    min_price, max_price = await resolve_price_threshold(session, "Hiç Olmayan Kategori", "cheap")

    assert (min_price, max_price) == (None, None)

"""backend/services/search/bm25.py için birim testler."""

import asyncio
from typing import cast

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import Business
from backend.services.search.bm25 import BM25Index, build_corpus, build_lexical_text, periodic_refresh_loop


def _make_business(
    business_id: int = 1,
    title: str = "Test Diş Kliniği",
    services: list[str] | None = None,
    rich_description: str | None = "İzmit'te güler yüzlü hizmet.",
    keywords: list[str] | None = None,
) -> Business:
    return Business(
        id=business_id,
        title=title,
        services=services if services is not None else ["dolgu", "kanal tedavisi"],
        rich_description=rich_description,
        keywords=keywords if keywords is not None else ["diş ağrısı", "diş hekimi"],
    )


def test_build_lexical_text_combines_title_services_description_and_keywords() -> None:
    business = _make_business()
    text = build_lexical_text(business)

    assert "Test Diş Kliniği" in text
    assert "dolgu" in text
    assert "kanal tedavisi" in text
    assert "İzmit'te güler yüzlü hizmet." in text
    assert "diş ağrısı" in text


def test_build_lexical_text_skips_missing_rich_description() -> None:
    business = _make_business(rich_description=None)
    text = build_lexical_text(business)

    assert "  " not in text  # boş parça yüzünden çift boşluk kalmamalı


def test_build_corpus_keeps_business_ids_and_documents_index_aligned() -> None:
    businesses = [
        _make_business(business_id=5, title="Alfa Kuaför", services=["saç kesimi"]),
        _make_business(business_id=9, title="Beta Berber", services=["sakal tıraşı"]),
    ]

    business_ids, documents = build_corpus(businesses)

    assert business_ids == [5, 9]
    assert "alfa" in documents[0]
    assert "beta" in documents[1]
    assert "sakal" not in documents[0]


def test_bm25_index_search_ranks_matching_business_first() -> None:
    businesses = [
        _make_business(
            business_id=1,
            title="Alfa Kuaför",
            services=["saç kesimi", "boya"],
            rich_description="Şık saç modelleri için Alfa Kuaför.",
            keywords=["saç boyama", "fön"],
        ),
        _make_business(
            business_id=2,
            title="Beta Diş Kliniği",
            services=["dolgu", "kanal tedavisi"],
            rich_description="Ağrısız kanal tedavisi uzmanı Beta Diş Kliniği.",
            keywords=["diş ağrısı", "diş hekimi"],
        ),
        # Üçüncü, alakasız bir işletme: 2 dokümanlık bir korpüste bir terim
        # dokümanların tam yarısında geçerse BM25'in IDF'i matematiksel
        # olarak sıfıra düşüyor (log(1.5)-log(1.5)=0) — N=2'ye özgü bir
        # dejenerasyon, 478 kayıtlık gerçek corpus'ta olmaz. Testi anlamlı
        # kılmak için korpüsü büyütüyoruz.
        _make_business(
            business_id=3,
            title="Gama Oto Yıkama",
            services=["araç yıkama"],
            rich_description="Hızlı ve temiz araç yıkama hizmeti.",
            keywords=["oto kuaför", "araç bakım"],
        ),
    ]
    index = BM25Index()
    index.build(businesses, fingerprint=(3, None))

    results = index.search("diş kanal tedavisi", top_k=10)

    assert results[0][0] == 2


def test_bm25_index_search_ranks_relevant_business_above_unrelated_one() -> None:
    businesses = [
        _make_business(
            business_id=1,
            title="Alfa Kuaför",
            services=["saç kesimi"],
            rich_description="Modern saç kesimi salonu.",
            keywords=["fön", "saç bakımı"],
        ),
        _make_business(
            business_id=2,
            title="Beta Diş Kliniği",
            services=["dolgu"],
            rich_description="Diş dolgusu ve muayene hizmeti.",
            keywords=["diş dolgusu", "muayene"],
        ),
    ]
    index = BM25Index()
    index.build(businesses, fingerprint=(2, None))

    results = index.search("saç kesimi", top_k=10)

    assert results[0][0] == 1


def test_bm25_index_search_respects_top_k_limit() -> None:
    businesses = [
        _make_business(
            business_id=i,
            title=f"İşletme {i}",
            services=[f"hizmet-{i}-a", f"hizmet-{i}-b"],
            rich_description=f"İşletme {i} için özel açıklama metni, berber hizmeti.",
            keywords=[f"anahtar-{i}"],
        )
        for i in range(1, 6)
    ]
    index = BM25Index()
    index.build(businesses, fingerprint=(5, None))

    results = index.search("berber", top_k=2)

    assert len(results) == 2


def test_bm25_index_search_returns_empty_list_when_not_built() -> None:
    index = BM25Index()

    assert index.search("herhangi bir sorgu", top_k=10) == []


def test_bm25_index_search_returns_empty_list_for_empty_query_tokens() -> None:
    businesses = [_make_business()]
    index = BM25Index()
    index.build(businesses, fingerprint=(1, None))

    assert index.search("!!!", top_k=10) == []


class _FakeSessionCtx:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> bool:
        return False


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionCtx:
        return _FakeSessionCtx()


async def test_periodic_refresh_loop_survives_transient_db_error_and_retries(monkeypatch) -> None:
    """Bir yenileme denemesi SQLAlchemyError ile başarısız olursa döngü
    çökmemeli, bir sonraki cycle'da tekrar denemeli."""
    sleep_count = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 3:
            # 3. sleep çağrısında kes: 1. ve 2. refresh denemesi zaten
            # tamamlanmış olur (sleep her zaman refresh'ten ÖNCE çağrılıyor,
            # 2. sleep'te kesersek 2. refresh hiç başlamamış olurdu).
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    index = BM25Index()
    call_count = 0

    async def fake_refresh_if_stale(session: object) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise SQLAlchemyError("geçici bağlantı hatası")
        return True

    monkeypatch.setattr(index, "refresh_if_stale", fake_refresh_if_stale)
    fake_factory = cast(async_sessionmaker[AsyncSession], _FakeSessionFactory())

    with pytest.raises(asyncio.CancelledError):
        await periodic_refresh_loop(index, fake_factory, interval_seconds=0)

    # 1. deneme hata verdi ama döngü devam etti, 2. deneme başarılı oldu
    assert call_count == 2

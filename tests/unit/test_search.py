"""backend/services/search.py için birim testler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.db.models import Business
from backend.services.search import (
    BM25Index,
    build_corpus,
    build_lexical_text,
    normalize_turkish_text,
    tokenize,
    vector_search,
)


class _FakeEmbeddingProvider:
    """embed_batch çağrısını gerçek OpenAI'ye gitmeden taklit eden test double'ı."""

    name = "fake"
    dimension = 3

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


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


def test_normalize_turkish_text_converts_dotted_i_to_lowercase_i() -> None:
    assert normalize_turkish_text("İZMİT") == "izmit"


def test_normalize_turkish_text_converts_dotless_i_to_lowercase_dotless_i() -> None:
    assert normalize_turkish_text("IŞIK") == "ışık"


def test_normalize_turkish_text_lowercases_turkish_specific_letters() -> None:
    assert normalize_turkish_text("AĞAÇ ÖĞÜT ÇEŞİT") == "ağaç öğüt çeşit"


def test_normalize_turkish_text_removes_punctuation() -> None:
    assert normalize_turkish_text("Merhaba, dünya!") == "merhaba  dünya "


def test_tokenize_splits_normalized_text_into_words() -> None:
    assert tokenize("Merhaba, dünya! İyi günler.") == ["merhaba", "dünya", "iyi", "günler"]


def test_tokenize_returns_empty_list_for_empty_string() -> None:
    assert tokenize("") == []


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


async def test_vector_search_returns_business_id_score_pairs() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(
        points=[SimpleNamespace(id=7, score=0.87), SimpleNamespace(id=3, score=0.65)]
    )

    results = await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    assert results == [(7, 0.87), (3, 0.65)]


async def test_vector_search_always_applies_is_active_filter() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[])

    await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    applied_filter = fake_client.query_points.call_args.kwargs["query_filter"]
    condition_keys = [condition.key for condition in applied_filter.must]
    assert "is_active" in condition_keys


async def test_vector_search_uses_provider_specific_collection_name() -> None:
    provider = _FakeEmbeddingProvider()
    fake_client = AsyncMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[])

    await vector_search(fake_client, provider, "diş kliniği", top_k=5)

    assert fake_client.query_points.call_args.kwargs["collection_name"] == "businesses_fake"

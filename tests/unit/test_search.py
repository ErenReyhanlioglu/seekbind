"""backend/services/search.py için birim testler."""

from backend.db.models import Business
from backend.services.search import (
    build_corpus,
    build_lexical_text,
    normalize_turkish_text,
    tokenize,
)


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

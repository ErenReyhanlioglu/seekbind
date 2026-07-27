"""backend/services/search/text.py için birim testler."""

from backend.services.search.text import normalize_turkish_text, tokenize


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

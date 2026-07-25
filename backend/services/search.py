"""Hybrid arama servisi.

Semantik (Qdrant/vektör) ve lexical (BM25) aramayı Reciprocal Rank
Fusion (RRF) ile birleştirir. Kesin filtreler (konum/gün/fiyat) Qdrant
payload filtering ile vektör aramasından önce uygulanır — bkz.
docs/roadmap.md "Önemli kararlar" bölümü.
"""

import re

_TURKISH_UPPERCASE_MAP: dict[str, str] = {"İ": "i", "I": "ı"}
_NON_WORD_PATTERN: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_turkish_text(text: str) -> str:
    """BM25 için metni küçük harfe çevirir ve noktalamayı temizler.

    Python'un yerleşik .lower()'ı Türkçe İ/I çiftini yanlış çevirir
    (İ -> 'i̇' iki karakter, I -> 'i' değil 'ı'); bu yüzden bu iki
    karakter önce özel eşlenir, kalanı (Ğ/Ş/Ç/Ö/Ü dahil) standart
    .lower() zaten doğru çeviriyor.
    """
    for uppercase, lowercase in _TURKISH_UPPERCASE_MAP.items():
        text = text.replace(uppercase, lowercase)
    text = text.lower()
    return _NON_WORD_PATTERN.sub(" ", text)


def tokenize(text: str) -> list[str]:
    """Normalize edilmiş metni BM25 için token listesine böler."""
    return normalize_turkish_text(text).split()

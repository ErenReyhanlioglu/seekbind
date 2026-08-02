"""Zemberek morfolojik analiz sarmalayıcısı — Türkçe eklemeli dil sorununu çözer.

Soru metnindeki bir kelime (`boyatmak`) ile kategori sözlüğündeki farklı
yüzey formunu (`boyama`) eşleştirmek için üç yöntem gerçek veride test
edildi (bkz. ADR-0027): ham substring eşleşmesi hiç yakalamadı, Snowball
stemmer türetimsel biçimleri (`boyatmak`↔`boyama`) kaçırdı, sabit uzunluk
prefix ise gerçek sözlükte yanlış-pozitif üretti (`hastalığı`≈`hastanesi`,
farklı kökler). Zemberek'in lemma kümesi kesişimi kuralı (belirsiz
kelimeler için birden fazla aday lemma döndürüp kümelerin kesişip
kesişmediğine bakmak) 6/6 bilinen test çiftinde doğru sonuç verdi —
tek-en-iyi-lemma yaklaşımı DEĞİL, bu yüzden `lemmas_of` bir küme döner.
"""

import re
from functools import lru_cache

from zemberek import TurkishMorphology

# Zemberek'in 'ge', 'ak', 'a' gibi belirsiz kısa kelimeler için ürettiği
# anlamsız/parça lemma'ları elemek üzere (bkz. ADR-0027).
MIN_LEMMA_LEN: int = 3

_WORD_PATTERN: re.Pattern[str] = re.compile(r"[a-zA-ZçÇğĞıİöÖşŞüÜ]+")


@lru_cache(maxsize=1)
def _get_morphology() -> TurkishMorphology:
    """Pahalı TurkishMorphology nesnesini singleton tutar (~4sn başlatma maliyeti)."""
    return TurkishMorphology.create_with_defaults()


def tr_lower(text: str) -> str:
    """Türkçe-farkındalıklı küçük harfe çevirme.

    Python'un varsayılan `.lower()`'ı 'İ' -> 'i' + birleşik nokta üretir,
    'I' -> 'i' yapar (Türkçe'de 'I''nın küçüğü 'ı' olmalı) — bu yüzden
    büyük/küçük harf farklı yazılmış aynı kelime (örn. "Kaş"/"kaş") ayrı
    lemma sayılıp gürültü üretiyordu, bu düzeltmeden önce.
    """
    return text.replace("İ", "i").replace("I", "ı").lower()


@lru_cache(maxsize=None)
def lemmas_of(word: str) -> frozenset[str]:
    """Bir kelimenin tüm aday lemma'larını döner (morfolojik belirsizlikte birden fazla)."""
    normalized = tr_lower(word)
    if len(normalized) < MIN_LEMMA_LEN:
        return frozenset()
    analyses = _get_morphology().analyze(normalized)
    return frozenset(
        tr_lower(analysis.item.lemma)
        for analysis in analyses
        if analysis.item.lemma and len(analysis.item.lemma) >= MIN_LEMMA_LEN
    )


def business_lemma_set(services: list[str], keywords: list[str]) -> set[str]:
    """Bir işletmenin `services`+`keywords` alanlarındaki tüm kelimelerin lemma kümesi."""
    all_lemmas: set[str] = set()
    for phrase in services + keywords:
        for word in _WORD_PATTERN.findall(phrase):
            all_lemmas |= lemmas_of(word)
    return all_lemmas

"""Kalıp bazlı prompt injection tespiti (bkz. ADR-0025).

`app.add_middleware()` ile kayıtlı bir ASGI middleware DEĞİL — sadece
`/recommend`'in raw_query'si bir LLM'e gidiyor, bu yüzden düz bir fonksiyon
olarak `rag/service.py::get_recommendation()`'ın en başında çağrılıyor.
Mevcut sistem-promptu savunmasıyla (system.txt) BİRLİKTE çalışır, onun
yerine geçmez.
"""

import re

from backend.services.search.text import tokenize

_NON_WORD_PATTERN: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # talimatları yok sayma (TR/EN)
    re.compile(r"önceki talimatları unut"),
    re.compile(r"kuralları (yok say|görmezden gel)"),
    re.compile(r"talimatları (unut|görmezden gel)"),
    re.compile(r"ignore (the |all )?(previous|above) instructions"),
    re.compile(r"disregard (the )?(above|previous)"),
    # sistem promptunu ifşa etme (TR/EN)
    re.compile(r"sistem prompt\w* (göster|yazdır|paylaş)"),
    re.compile(r"talimatlarını (göster|yazdır|paylaş)"),
    re.compile(r"(show|reveal|print) (me )?your (system )?prompt"),
    re.compile(r"reveal your instructions"),
    # rol değiştirme (TR/EN)
    re.compile(r"\w+ (gibi|olarak) davran\b"),
    re.compile(r"yeni bir rol üstlen\b"),
    re.compile(r"sen artık"),
    re.compile(r"you are now a"),
    re.compile(r"act as if you (are|re)"),
    re.compile(r"pretend to be"),
    re.compile(r"from now on you are"),
)


def detect_prompt_injection(raw_query: str) -> bool:
    """`raw_query`'de bilinen bir injection kalıbı var mı kontrol eder.

    İKİ ayrı normalizasyona karşı kontrol edilir:
    1. `tokenize()` (mevcut BM25 normalizasyonu, search/text.py) — Türkçe
       İ/I çiftini doğru çevirir (İ->i, I->ı), Türkçe kalıplar için gerekli.
    2. Düz `str.lower()` + noktalama temizliği — `tokenize()`'ın Türkçe I->ı
       eşlemesi İngilizce metni KIRAR: "Ignore..." gibi büyük I ile başlayan
       bir cümle "ıgnore" olur ve İngilizce kalıplarla asla eşleşmez (gerçek
       smoke test'te (`smoke_test_prompt_injection.py`) hem gpt-4o-mini hem
       qwen3'e karşı doğrulanmış bir hata — "Ignore all previous
       instructions..." filtreden kaçıyordu). Bu ikinci normalizasyon o
       kaçağı kapatıyor.

    Her iki normalizasyon da TÜM kalıplara karşı kontrol ediliyor (sadece
    kendi "dili"ne değil) — Türkçe kalıplar düz `lower()`'a karşı da büyük
    ölçüde çalışır (Ğ/Ş/Ç/Ö/Ü için sorun yok, sadece İ/I için `tokenize()`
    gerekli), İngilizce kalıplar zaten `tokenize()`'a karşı da çoğu zaman
    çalışır — `or` ile birleştirmek, ikisinin de kaçırdığı çok az sayıda
    (çift kırılma gerektiren) durum dışında hepsini yakalar.
    """
    turkish_aware = " ".join(tokenize(raw_query))
    plain = _NON_WORD_PATTERN.sub(" ", raw_query.lower())
    return any(pattern.search(turkish_aware) or pattern.search(plain) for pattern in _INJECTION_PATTERNS)

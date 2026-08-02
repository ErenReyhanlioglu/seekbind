"""Kapsam oranı + entropi tabanlı ikili bölünme değerlendirmesi.

`ragas_testset` paketinin çekirdek istatistiksel primitive'i — bir
yüklemin (terim, fiyat eşiği, gün/saat, cinsiyet vb.) bir kategori
içinde gerçekten ayırt edici olup olmadığına karar vermek için
`term_distinctiveness.py`, `price_distinctiveness.py` ve
`combination_search.py` tarafından ortak kullanılır (bkz. ADR-0027).

ÖNEMLİ: Bu bir hipotez testi DEĞİL, tanımlayıcı bir istatistik — p-değeri
üretmiyor, çoklu test düzeltmesi (FDR/Bonferroni) gerektirmiyor. Entropi,
HANGİ işletmelerin eşleştiğine değil sadece SAYIYA bağlı — bu yüzden
"şans eseri mi" sorusu anlamsız (permütasyon deneyiyle doğrulandı, bkz.
ADR-0027). `MIN_COUNT` eşiği simetrik uygulanır (hem eşleşen hem
eşleşMEyen taraf ≥MIN_COUNT) — bu, entropiyi her iki dejenere uçtan
(≈0 ve ≈1) otomatik uzak tutar, ayrı bir "entropi eşiği" icat etmeye
gerek kalmaz.
"""

from math import log2

from pydantic import BaseModel

# 1 eşleşme named_business intent'iyle çakışır, 2 belirsiz, 3+ gerçek
# bir "seçenek sun" senaryosu sayılır (bkz. ADR-0027).
MIN_COUNT: int = 3


class SplitResult(BaseModel):
    """Bir yüklemin kategori içindeki ikili bölünmesinin özeti."""

    matched_count: int
    total_count: int
    fraction: float
    entropy: float
    is_viable: bool


def entropy(fraction: float) -> float:
    """Shannon entropisi, [0, 1] aralığında (bit cinsinden), f=0.5'te maksimum."""
    if fraction <= 0.0 or fraction >= 1.0:
        return 0.0
    return -(fraction * log2(fraction) + (1 - fraction) * log2(1 - fraction))


def evaluate_split(matched_count: int, total_count: int) -> SplitResult:
    """Bir yüklemin kategori içindeki kapsamını simetrik MIN_COUNT'a karşı değerlendirir."""
    if total_count <= 0:
        raise ValueError("total_count sıfırdan büyük olmalı")
    unmatched_count = total_count - matched_count
    fraction = matched_count / total_count
    is_viable = matched_count >= MIN_COUNT and unmatched_count >= MIN_COUNT
    return SplitResult(
        matched_count=matched_count,
        total_count=total_count,
        fraction=fraction,
        entropy=entropy(fraction),
        is_viable=is_viable,
    )

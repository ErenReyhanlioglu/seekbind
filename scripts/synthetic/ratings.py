"""Yorum sayısı temizliği ve Bayesian düzeltilmiş puan hesaplama.

SerpAPI'nin sayısal `reviews` alanı Türkçe "B" (bin) ekini yanlış parse
edebiliyor (örn. "(1,3 B)" -> 1300000000), bu yüzden kaynak olarak her
zaman reviews_original metni kullanılır. weighted_rating ise az yorumlu
işletmelerin yüksek puanla yanıltıcı şekilde öne çıkmasını engeller.
"""

import re
from typing import Any

# "(384)" ya da "(1,3 B)" gibi metinlerden sayıyı ve varsa "B" (bin) ekini yakalar
REVIEW_COUNT_PATTERN = re.compile(r"\(([\d.,]+)\s*(B)?\)", re.IGNORECASE)


def parse_review_count(reviews_original: str | None, fallback: int) -> int:
    """reviews_original metninden doğru yorum sayısını çıkarır."""
    if not reviews_original:
        return fallback
    match = REVIEW_COUNT_PATTERN.search(reviews_original)
    if not match:
        return fallback
    number_str, bin_suffix = match.groups()
    number_str = number_str.replace(".", "").replace(",", ".")
    try:
        value = float(number_str)
    except ValueError:
        return fallback
    if bin_suffix:
        value *= 1000
    return int(round(value))


def compute_rating_baseline(raw_records: list[dict[str, Any]]) -> tuple[float, int]:
    """Bayesian düzeltme için tüm veri setinden C (ortalama puan) ve m (medyan
    yorum sayısı, güven eşiği) hesaplar.
    """
    ratings: list[float] = []
    review_counts: list[int] = []
    for raw in raw_records:
        data = raw["data"]
        rating = data.get("rating")
        if rating is None:
            continue
        ratings.append(rating)
        review_counts.append(parse_review_count(data.get("reviews_original"), data.get("reviews", 0)))

    mean_rating = sum(ratings) / len(ratings)
    review_counts.sort()
    median_reviews = review_counts[len(review_counts) // 2]
    return mean_rating, median_reviews


def compute_weighted_rating(
    rating: float | None,
    reviews: int,
    mean_rating: float,
    confidence_m: int,
) -> float | None:
    """IMDB tarzı Bayesian düzeltilmiş puan: az yorumlu işletmeleri genel
    ortalamaya doğru çeker, çok yorumlu işletmelerin kendi puanına güvenir.
    """
    if rating is None:
        return None
    return (reviews / (reviews + confidence_m)) * rating + (
        confidence_m / (reviews + confidence_m)
    ) * mean_rating

"""Kategori sözlüğünden ayırt edici aday servis terimlerini çıkarır (problem #1, ADR-0027).

Bir kategorinin `services`+`keywords` sözlüğündeki her lemma için
kategori-içi kapsam oranı ve entropi hesaplanır (bkz.
`coverage_stats.py`) — sadece MIN_COUNT'u simetrik geçen (ne çok nadir
ne neredeyse evrensel) terimler "gerçekten ayırt edici" sayılır. Bu,
`build_ragas_ground_truth.py`'deki `service_keyword` sert filtresinin
hangi terimlerle uygulanabileceğine karar vermek için kullanılır.
"""

from collections import defaultdict

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from scripts.ragas_testset.business_lookup import fetch_category_businesses
from scripts.ragas_testset.coverage_stats import SplitResult, evaluate_split
from scripts.ragas_testset.turkish_lemma import business_lemma_set


class TermCandidate(BaseModel):
    """Bir kategori içinde ayırt edici bulunan aday servis terimi (lemma)."""

    lemma: str
    matched_ids: frozenset[int]
    split: SplitResult


def _rank_lemmas(businesses: list[Business]) -> list[TermCandidate]:
    """İşletme listesinden lemma -> eşleşen id kümesini çıkarıp entropiye göre sıralar."""
    lemma_to_ids: dict[str, set[int]] = defaultdict(set)
    for business in businesses:
        for lemma in business_lemma_set(business.services, business.keywords):
            lemma_to_ids[lemma].add(business.id)

    total = len(businesses)
    candidates = [
        TermCandidate(
            lemma=lemma,
            matched_ids=frozenset(ids),
            split=evaluate_split(len(ids), total),
        )
        for lemma, ids in lemma_to_ids.items()
    ]
    viable = [c for c in candidates if c.split.is_viable]
    viable.sort(key=lambda c: (-c.split.entropy, -c.split.matched_count))
    return viable


async def scan_category(session: AsyncSession, category: str) -> list[TermCandidate]:
    """Bir kategorinin gerçek servis/anahtar kelime sözlüğünden ayırt edici terimleri çıkarır."""
    businesses = await fetch_category_businesses(session, category)
    return _rank_lemmas(businesses)

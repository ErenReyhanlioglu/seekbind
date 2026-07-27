"""Hybrid arama servisi.

Semantik (Qdrant/vektör) ve lexical (BM25) aramayı Reciprocal Rank
Fusion (RRF) ile birleştirir. Kesin filtreler (konum/gün/fiyat) Qdrant
payload filtering ile vektör aramasından önce uygulanır — bkz.
docs/roadmap.md "Önemli kararlar" bölümü.

Alt modüller: text (normalizasyon), bm25 (lexical index), vector
(semantik arama), filters (SearchFilters), availability (tarih/saat
müsaitliği, iki fazlı filtrelemenin ikinci fazı), fusion (RRF).
"""

from backend.services.search.availability import (
    DateAvailabilityFilter,
    fetch_available_business_ids,
)
from backend.services.search.bm25 import (
    BM25Index,
    build_corpus,
    build_lexical_text,
    compute_fingerprint,
    fetch_active_businesses,
    get_bm25_index,
)
from backend.services.search.filters import NearFilter, SearchFilters, translate_filters_to_qdrant
from backend.services.search.fusion import reciprocal_rank_fusion
from backend.services.search.text import normalize_turkish_text, tokenize
from backend.services.search.vector import vector_search

__all__ = [
    "BM25Index",
    "DateAvailabilityFilter",
    "NearFilter",
    "SearchFilters",
    "build_corpus",
    "build_lexical_text",
    "compute_fingerprint",
    "fetch_active_businesses",
    "fetch_available_business_ids",
    "get_bm25_index",
    "normalize_turkish_text",
    "reciprocal_rank_fusion",
    "tokenize",
    "translate_filters_to_qdrant",
    "vector_search",
]

"""Hybrid arama servisi.

Semantik (Qdrant/vektör) ve lexical (BM25) aramayı Reciprocal Rank
Fusion (RRF) ile birleştirir. Kesin filtreler (konum/gün/fiyat) Qdrant
payload filtering ile vektör aramasından önce uygulanır — bkz.
docs/roadmap.md "Önemli kararlar" bölümü.

Alt modüller: text (normalizasyon), bm25 (lexical index), vector
(semantik arama), filters (SearchFilters), availability (tarih/saat
müsaitliği, iki fazlı filtrelemenin ikinci fazı), fusion (RRF), service
(hepsini birleştiren search_providers orkestrasyonu).
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
    periodic_refresh_loop,
)
from backend.services.search.filters import (
    NearFilter,
    SearchFilters,
    compute_distance_km,
    translate_filters_to_qdrant,
)
from backend.services.search.fusion import reciprocal_rank_fusion
from backend.services.search.service import search_providers
from backend.services.search.text import normalize_turkish_text, tokenize
from backend.services.search.vector import fetch_filtered_business_ids, vector_search

__all__ = [
    "BM25Index",
    "DateAvailabilityFilter",
    "NearFilter",
    "SearchFilters",
    "build_corpus",
    "build_lexical_text",
    "compute_distance_km",
    "compute_fingerprint",
    "fetch_active_businesses",
    "fetch_available_business_ids",
    "fetch_filtered_business_ids",
    "get_bm25_index",
    "normalize_turkish_text",
    "periodic_refresh_loop",
    "reciprocal_rank_fusion",
    "search_providers",
    "tokenize",
    "translate_filters_to_qdrant",
    "vector_search",
]

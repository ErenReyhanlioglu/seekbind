"""Qdrant üzerinde semantik (vektör) arama."""

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Condition, FieldCondition, Filter, MatchValue

from backend.services.embedding import EmbeddingProvider, get_qdrant_collection_name


def _build_active_only_filter(extra_filter: Filter | None) -> Filter:
    """is_active=true zorunlu koşulunu, varsa ek filtre koşullarıyla birleştirir.

    is_active her arama isteğinde uygulanmalı — çağıranın SearchFilters'a
    eklemeyi unutabileceği bir kısıt değil, aramanın kendisinin garantisi.

    Qdrant'ın Filter.must alanı tek bir Condition ya da Condition listesi
    olabilir (List değil) — sadece liste varsayıp .extend() çağırmak, tekil
    bir Condition geldiğinde (örn. ileride translate_filters_to_qdrant tek
    koşullu bir filtre üretirse) sessizce yanlış davranırdı.
    """
    must_conditions: list[Condition] = [
        FieldCondition(key="is_active", match=MatchValue(value=True))
    ]
    if extra_filter is not None and extra_filter.must is not None:
        extra_must = extra_filter.must
        if isinstance(extra_must, list):
            must_conditions.extend(extra_must)
        else:
            must_conditions.append(extra_must)
    return Filter(must=must_conditions)


async def vector_search(
    client: AsyncQdrantClient,
    provider: EmbeddingProvider,
    query: str,
    top_k: int,
    extra_filter: Filter | None = None,
) -> list[tuple[int, float]]:
    """Qdrant'ta semantik arama yapar, (business_id, skor) çiftlerini azalan skora göre döner."""
    [query_vector] = await provider.embed_batch([query])
    collection_name = get_qdrant_collection_name(provider)
    response = await client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=_build_active_only_filter(extra_filter),
        limit=top_k,
        with_payload=False,
    )
    # point.id Qdrant'ta ExtendedPointId (int | UUID str) — bu projede
    # her zaman business.id (int) olarak upsert edildiği için (bkz.
    # load_embeddings.py) int()'e daraltmak güvenli.
    return [(int(point.id), point.score) for point in response.points]


SCROLL_PAGE_SIZE: int = 200


async def fetch_filtered_business_ids(
    client: AsyncQdrantClient,
    provider: EmbeddingProvider,
    extra_filter: Filter | None,
) -> set[int]:
    """extra_filter'ı (varsa) sağlayan tüm işletme ID'lerini vektör araması yapmadan döner.

    rank-bm25 kendi başına payload filtering desteklemiyor — BM25 sonuçlarını
    SearchFilters ile kısıtlamak için bu küme ile kesişim alınır (bkz. service.py).
    Sadece extra_filter dolu olduğunda çağrılmalı; boşsa BM25 corpus'u zaten
    sadece aktif işletmelerden kurulu (bkz. bm25.fetch_active_businesses),
    ekstra bir sorguya gerek yok.
    """
    collection_name = get_qdrant_collection_name(provider)
    ids: set[int] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=collection_name,
            scroll_filter=_build_active_only_filter(extra_filter),
            limit=SCROLL_PAGE_SIZE,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.update(int(point.id) for point in points)
        if offset is None:
            break
    return ids

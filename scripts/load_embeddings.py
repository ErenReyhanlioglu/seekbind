"""Postgres'teki işletme verisini embed edip Qdrant'a yükler.

Metin artık Postgres'ten (businesses tablosu) okunur — doğruluk kaynağı
orası. Her embedding sağlayıcısı için ayrı bir Qdrant collection
kullanılır (businesses_<sağlayıcı adı>), model değişince eskisini
silmeye gerek kalmaz. business.id, Qdrant point ID'si olarak
kullanılır (kalıcı kimlik → upsert doğal, truncate-and-load'a gerek yok).
"""

import asyncio
import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business
from backend.db.qdrant import get_qdrant_client
from backend.db.session import get_session_factory
from backend.services.embedding import EmbeddingProvider, get_embedding_provider

logger = logging.getLogger(__name__)

COLLECTION_PREFIX: str = "businesses"
EMBEDDING_BATCH_SIZE: int = 50


def build_embedding_text(business: Business) -> str:
    """İşletme kaydından, embedding'e girecek yapılandırılmış metni üretir.

    En önemli bilgi (başlık) en başta olur ki metin çok uzayıp
    kesilirse (truncation) kaybolmasın.
    """
    parts = [
        business.title,
        f"Hizmetler: {', '.join(business.services)}" if business.services else "",
        business.rich_description or "",
        f"Anahtar kelimeler: {', '.join(business.keywords)}" if business.keywords else "",
    ]
    return "\n".join(part for part in parts if part)


def build_payload(business: Business) -> dict:
    """Qdrant point'ine eklenecek, sorgu anında filtrelenebilecek payload'ı üretir."""
    return {
        "place_id": business.place_id,
        "type_normalized": business.type_normalized,
        "price_min": business.price_min,
        "price_max": business.price_max,
        "online_available": business.online_available,
        "gender": business.gender,
        "tags": business.tags,
    }


def chunk(items: list, size: int) -> list[list]:
    """Bir listeyi sabit boyutlu parçalara böler."""
    return [items[i : i + size] for i in range(0, len(items), size)]


async def load_all_businesses(session: AsyncSession) -> list[Business]:
    """businesses tablosundaki tüm kayıtları okur."""
    result = await session.execute(select(Business))
    return list(result.scalars().all())


async def ensure_collection(client: AsyncQdrantClient, collection_name: str, dimension: int) -> None:
    """Collection yoksa oluşturur, varsa dokunmaz."""
    exists = await client.collection_exists(collection_name)
    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
        )
        logger.info("Collection oluşturuldu: %s (boyut=%d)", collection_name, dimension)


async def embed_and_upsert_batch(
    client: AsyncQdrantClient,
    collection_name: str,
    provider: EmbeddingProvider,
    businesses: list[Business],
) -> None:
    """Bir batch işletmeyi embed edip Qdrant'a upsert eder."""
    texts = [build_embedding_text(b) for b in businesses]
    vectors = await provider.embed_batch(texts)
    points = [
        PointStruct(id=business.id, vector=vector, payload=build_payload(business))
        for business, vector in zip(businesses, vectors, strict=True)
    ]
    await client.upsert(collection_name=collection_name, points=points)


async def main() -> None:
    """Tüm işletmeleri embed edip Qdrant'a yükler."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    provider = get_embedding_provider()
    qdrant_client = get_qdrant_client()
    collection_name = f"{COLLECTION_PREFIX}_{provider.name}"

    await ensure_collection(qdrant_client, collection_name, provider.dimension)

    session_factory = get_session_factory()
    async with session_factory() as session:
        businesses = await load_all_businesses(session)
    logger.info("%d işletme okundu, '%s' collection'ına yüklenecek", len(businesses), collection_name)

    batches = chunk(businesses, EMBEDDING_BATCH_SIZE)
    for i, batch in enumerate(batches, start=1):
        await embed_and_upsert_batch(qdrant_client, collection_name, provider, batch)
        logger.info("Batch %d/%d yüklendi (%d işletme)", i, len(batches), len(batch))

    logger.info("Tamamlandı. %d işletme '%s' collection'ına yüklendi", len(businesses), collection_name)


if __name__ == "__main__":
    asyncio.run(main())

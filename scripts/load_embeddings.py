"""Postgres'teki işletme verisini embed edip Qdrant'a yükler.

Metin artık Postgres'ten (businesses tablosu) okunur — doğruluk kaynağı
orası. Her embedding sağlayıcısı için ayrı bir Qdrant collection
kullanılır (businesses_<sağlayıcı adı>), model değişince eskisini
silmeye gerek kalmaz. business.id, Qdrant point ID'si olarak
kullanılır (kalıcı kimlik → upsert doğal, truncate-and-load'a gerek yok).
"""

import argparse
import asyncio
import logging
from typing import Literal

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, GeoPoint, PayloadSchemaType, PointStruct, VectorParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.db.models import Business
from backend.db.qdrant import get_qdrant_client
from backend.db.redis import get_redis_client
from backend.db.session import get_session_factory
from backend.services.cache import CachedEmbeddingProvider
from backend.services.embedding import (
    EmbeddingProvider,
    OllamaEmbedding,
    OpenAIEmbedding,
    get_embedding_provider,
    get_qdrant_collection_name,
)

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE: int = 50


def _build_provider(provider_name: Literal["openai", "ollama"]) -> EmbeddingProvider:
    """CLI'den seçilen sağlayıcıyı (cache'lenmiş olarak) döner.

    `openai` -> `get_embedding_provider(allow_fallback=False)` ile birebir
    aynı (canlı sistemin kullandığı yol). `ollama` sadece bu script'e özgü
    bir seçenek — canlı sistemde "aktif embedding sağlayıcısı" diye bir ayar
    bilinçli olarak yok (bkz. ADR-0023), ama Ollama'nın fallback collection'ını
    (`businesses_ollama-*`) doldurmak için bu script'in Ollama'ya elle
    yönlendirilebilmesi gerekiyor.
    """
    if provider_name == "ollama":
        settings = get_settings()
        return CachedEmbeddingProvider(
            OllamaEmbedding(),
            get_redis_client(),
            enabled=settings.enable_cache,
            ttl_seconds=settings.embedding_cache_ttl_seconds,
        )
    return get_embedding_provider(allow_fallback=False)


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


def is_open_weekend(working_hours: dict) -> bool:
    """Cumartesi ya da pazar açılış saati tanımlıysa True döner.

    scripts/synthetic/tags.py'deki "hafta sonu açık" etiketiyle aynı
    mantık — yeni bir hesaplama icat etmiyoruz.
    """
    saturday_open = working_hours.get("saturday", {}).get("open")
    sunday_open = working_hours.get("sunday", {}).get("open")
    return saturday_open is not None or sunday_open is not None


def build_geo_point(business: Business) -> GeoPoint | None:
    """İşletmenin koordinatlarından Qdrant GeoPoint'i üretir, koordinat yoksa None döner."""
    if business.latitude is None or business.longitude is None:
        return None
    return GeoPoint(lon=business.longitude, lat=business.latitude)


def build_payload(business: Business) -> dict:
    """Qdrant point'ine eklenecek, sorgu anında filtrelenebilecek payload'ı üretir."""
    payload: dict = {
        "place_id": business.place_id,
        "type_normalized": business.type_normalized,
        "price_min": business.price_min,
        "price_max": business.price_max,
        "online_available": business.online_available,
        "gender": business.gender,
        "tags": business.tags,
        "is_active": business.is_active,
        "open_weekend": is_open_weekend(business.working_hours),
    }
    geo_point = build_geo_point(business)
    if geo_point is not None:
        payload["location"] = geo_point.model_dump()
    return payload


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


async def ensure_geo_index(client: AsyncQdrantClient, collection_name: str) -> None:
    """'location' alanı için geo payload index'i kurar (yoksa oluşturur, varsa dokunmaz).

    GeoRadius filtresiyle konum bazlı arama yapabilmek için gerekli —
    478 kayıtta zorunlu değil ama doğru pratik, veri büyüdükçe sorun
    çıkarmaz. create_payload_index zaten var olan bir index için
    çağrılırsa no-op'tur (idempotent).
    """
    await client.create_payload_index(
        collection_name=collection_name,
        field_name="location",
        field_schema=PayloadSchemaType.GEO,
    )


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


async def main(provider_name: Literal["openai", "ollama"] = "openai") -> None:
    """Tüm işletmeleri embed edip Qdrant'a yükler.

    `provider_name="openai"` (varsayılan): canlı sistemin de kullandığı yol,
    fallback KAPALI (bkz. `_build_provider` docstring'i — OpenAI geçici
    ulaşılamazken bir kısım vektörün sessizce Ollama'nın farklı anlamsal
    uzayından aynı collection'a yazılması testle yakalanamayan kalıcı bir
    veri bozulması olurdu, toplu yükleme fail-fast başarısız olmalı).
    `provider_name="ollama"`: sadece bu script'e özgü, fallback collection'ını
    (`businesses_ollama-*`) elle doldurmak için.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    provider = _build_provider(provider_name)
    qdrant_client = get_qdrant_client()
    collection_name = get_qdrant_collection_name(provider)

    await ensure_collection(qdrant_client, collection_name, provider.dimension)
    await ensure_geo_index(qdrant_client, collection_name)

    session_factory = get_session_factory()
    async with session_factory() as session:
        businesses = await load_all_businesses(session)
    logger.info("%d işletme okundu, '%s' collection'ına yüklenecek", len(businesses), collection_name)

    batches = chunk(businesses, EMBEDDING_BATCH_SIZE)
    for i, batch in enumerate(batches, start=1):
        await embed_and_upsert_batch(qdrant_client, collection_name, provider, batch)
        logger.info("Batch %d/%d yüklendi (%d işletme)", i, len(batches), len(batch))

    logger.info("Tamamlandı. %d işletme '%s' collection'ına yüklendi", len(businesses), collection_name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=["openai", "ollama"],
        default="openai",
        help="Hangi embedding sağlayıcısıyla yüklenecek (varsayılan: openai)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(provider_name=args.provider))

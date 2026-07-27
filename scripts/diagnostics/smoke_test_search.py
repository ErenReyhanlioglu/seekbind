"""feature/search-service için gerçek DB/Qdrant'a karşı manuel doğrulama script'i.

Otomatik test değil — gerçek 478 işletmelik veri üzerinde birkaç örnek
sorgunun mantıklı sonuç verip vermediğini gözle kontrol etmek içindir.
Gerçek bir OpenAI embedding çağrısı (~birkaç sorgu, önemsiz maliyet) yapar.

DISPLAY_LIMIT=40 ile tüm aday havuzu gösterilir (candidate pool cap'i ile
aynı) — sadece ilk birkaç sonuca değil, RRF'nin bulduğu her şeye bakabilmek
için. _diagnose_query, BM25 ve vektörün ayrı ayrı ne döndürdüğünü gösterir —
"alakasız bir sonuç hangi taraftan, kaçıncı sıradan geldi" sorusuna tahmin
değil, gerçek veriyle cevap vermek için.

Sonuçlar evaluation/results/diagnostics/search_smoke_test/<etiket_>zaman_
damgası.json'a yazılır — her çalıştırma zaman damgalı olduğu için hiçbir
sonuç sessizce ezilmez, opsiyonel etiket (sys.argv[1], örn. `before_reranker`)
dosyaya semantik anlam katar ("bu hangi kilometre taşıydı" sorusuna zaman
damgası tek başına cevap vermez). Diagnostic script'lerinin her biri kendi
alt klasörüne yazar (bkz. check_embedding_diversity.py'deki embedding_diversity/
alt klasörü) ki sonuç dosyaları birbirine karışmasın.
"""

import asyncio
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import ProviderResult
from backend.db.models import Business
from backend.db.qdrant import get_qdrant_client
from backend.db.session import get_session_factory
from backend.services.embedding import EmbeddingProvider, get_embedding_provider
from backend.services.search import (
    BM25Index,
    DateAvailabilityFilter,
    NearFilter,
    SearchFilters,
    search_providers,
    translate_filters_to_qdrant,
    vector_search,
)

logger = logging.getLogger(__name__)

DISPLAY_LIMIT: int = 40
DIAGNOSTIC_DEPTH: int = 15
RESULTS_DIR: Path = Path("evaluation/results/diagnostics/search_smoke_test")
# Windows dosya sisteminde ":" geçersiz — ISO 8601'in saat kısmındaki
# iki nokta üst üste yerine tire kullanan bir format gerekiyor.
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"

# İzmit merkez civarı bir koordinat — konum filtresini test etmek için
IZMIT_MERKEZ_LAT: float = 40.7654
IZMIT_MERKEZ_LON: float = 29.9408


def _print_and_record(title: str, results: list[ProviderResult], total: int) -> dict:
    """Sonucu terminale yazdırır, JSON'a kaydedilecek yapıyı da döner."""
    print(f"\n=== {title} (havuzda toplam {total} aday) ===")
    if not results:
        print("  (sonuç yok)")
    for i, result in enumerate(results, start=1):
        distance = f", {result.distance_km:.1f} km" if result.distance_km is not None else ""
        print(
            f"  {i}. {result.title} — {result.price_min}-{result.price_max}TL, "
            f"puan={result.rating}{distance}"
        )
    return {
        "title": title,
        "total_candidates": total,
        "results": [
            {
                "rank": i,
                "title": r.title,
                "price_min": r.price_min,
                "price_max": r.price_max,
                "rating": r.rating,
                "distance_km": r.distance_km,
            }
            for i, r in enumerate(results, start=1)
        ],
    }


async def _lookup_titles(session: AsyncSession, business_ids: list[int]) -> dict[int, str]:
    """Sadece ID/skor içeren ham arama sonuçlarını gözle okunabilir yapmak için başlıkları çeker."""
    if not business_ids:
        return {}
    result = await session.execute(select(Business.id, Business.title).where(Business.id.in_(business_ids)))
    return {business_id: title for business_id, title in result.all()}


async def _diagnose_query(
    session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    query: str,
    filters: SearchFilters,
) -> dict:
    """BM25 ve vektörün HAM (RRF öncesi) top-N'ini ayrı ayrı yazdırır ve döner.

    search_providers'ın tek başına dönmediği bir bilgi: bir sonuç RRF'ye
    hangi taraftan, kaçıncı sıradan girdi. "Alakasız sonuç nereden geldi"
    sorusunu tahmin değil, gerçek sıralamayla cevaplamak için.
    """
    qdrant_filter = translate_filters_to_qdrant(filters)

    vector_results = await vector_search(
        qdrant_client, embedding_provider, query, DIAGNOSTIC_DEPTH, qdrant_filter
    )
    bm25_results = bm25_index.search(query, DIAGNOSTIC_DEPTH)

    all_ids = [bid for bid, _ in vector_results] + [bid for bid, _ in bm25_results]
    titles = await _lookup_titles(session, all_ids)

    print(f"\n--- Tanı: '{query}' (filtre: {filters.model_dump(exclude_none=True)}) ---")
    print(f"  Vektör top-{DIAGNOSTIC_DEPTH}:")
    for rank, (bid, score) in enumerate(vector_results, start=1):
        print(f"    {rank}. {titles.get(bid, '?')} (skor={score:.3f})")
    print(f"  BM25 top-{DIAGNOSTIC_DEPTH}:")
    for rank, (bid, score) in enumerate(bm25_results, start=1):
        print(f"    {rank}. {titles.get(bid, '?')} (skor={score:.3f})")

    return {
        "query": query,
        "filters": filters.model_dump(exclude_none=True),
        "vector_top": [{"rank": r, "title": titles.get(bid, "?"), "score": score} for r, (bid, score) in enumerate(vector_results, start=1)],
        "bm25_top": [{"rank": r, "title": titles.get(bid, "?"), "score": score} for r, (bid, score) in enumerate(bm25_results, start=1)],
    }


def _write_result(scenarios: list[dict], diagnostics: list[dict], label: str | None) -> Path:
    """Sonucu evaluation/results/diagnostics/search_smoke_test/ altına JSON olarak yazar.

    Dosya adı her zaman zaman damgalı (hiçbir sonuç sessizce ezilmez);
    opsiyonel etiket verilirse ("before_reranker" gibi) dosya adının başına
    eklenir, ileride dosya listesinde "bu hangi kilometre taşıydı" diye
    aramayı kolaylaştırır.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
    filename = f"{label}_{timestamp}.json" if label else f"{timestamp}.json"
    output_path = RESULTS_DIR / filename
    payload = {"label": label, "timestamp": timestamp, "scenarios": scenarios, "diagnostics": diagnostics}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


async def main(label: str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    qdrant_client = get_qdrant_client()
    embedding_provider = get_embedding_provider()
    session_factory = get_session_factory()

    scenarios: list[dict] = []
    diagnostics: list[dict] = []

    bm25_index = BM25Index()
    async with session_factory() as session:
        await bm25_index.refresh_if_stale(session)
        logger.info("BM25 index kuruldu")

        async def run(
            title: str,
            query: str,
            filters: SearchFilters,
            availability: DateAvailabilityFilter | None = None,
        ) -> None:
            response = await search_providers(
                session=session,
                qdrant_client=qdrant_client,
                bm25_index=bm25_index,
                embedding_provider=embedding_provider,
                query=query,
                filters=filters,
                availability=availability,
                limit=DISPLAY_LIMIT,
            )
            scenarios.append(_print_and_record(title, response.results, response.total))

        # 1) Sade semantik + fiyat filtresi
        await run("Ucuz diş kliniği (max_price=1500)", "ucuz diş kliniği", SearchFilters(max_price=1500))

        # 1b) Aynı sorgu, fiyat filtresi OLMADAN — karşılaştırma için
        await run("Ucuz diş kliniği (filtresiz)", "ucuz diş kliniği", SearchFilters())

        # 1c) Tanı: max_price=1500 ile BM25/vektör ham sonuçları
        diagnostics.append(
            await _diagnose_query(
                session, qdrant_client, bm25_index, embedding_provider, "ucuz diş kliniği", SearchFilters(max_price=1500)
            )
        )

        # 2) Kategori + cinsiyet filtresi
        await run(
            "Kadınlara yönelik kuaför", "saç kesimi", SearchFilters(category="Kuaför", gender="female")
        )

        # 2b) Başka bir "ucuz X" kombinasyonu — bu bir kalıp mı yoksa tek seferlik mi görmek için
        await run("Ucuz kuaför (max_price=1000)", "ucuz kuaför", SearchFilters(max_price=1000))

        # 3) Hafta sonu açık filtresi
        await run("Hafta sonu açık güzellik salonu", "güzellik salonu", SearchFilters(weekend_open_only=True))

        # 4) Konum filtresi (mesafe kontrolü için)
        await run(
            "İzmit merkeze 5km içinde berber",
            "berber",
            SearchFilters(near=NearFilter(latitude=IZMIT_MERKEZ_LAT, longitude=IZMIT_MERKEZ_LON, radius_km=5)),
        )

        # 5) Tarih/saat müsaitliği (iki fazlı filtrenin gerçek testi)
        tomorrow = date.today() + timedelta(days=1)
        await run(
            f"Diş kliniği, {tomorrow} sabahı müsait",
            "diş kliniği",
            SearchFilters(),
            availability=DateAvailabilityFilter(date=tomorrow, time_of_day="morning"),
        )

        # 6) Fiyat aralığının iki ucu da verilirse
        await run("Diş kliniği (1000-3000TL aralığı)", "diş kliniği", SearchFilters(min_price=1000, max_price=3000))

        # 7) Muhtemelen boş dönecek bir kombinasyon — zarif davranış kontrolü
        await run("Diş kliniği (max_price=10, muhtemelen boş)", "diş kliniği", SearchFilters(max_price=10))

    output_path = _write_result(scenarios, diagnostics, label)
    logger.info("Sonuçlar kaydedildi: %s", output_path)
    logger.info("Smoke test tamamlandı.")


if __name__ == "__main__":
    label_arg = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(label_arg))

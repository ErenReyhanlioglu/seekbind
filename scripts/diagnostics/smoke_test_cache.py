"""feature/cache-layer için gerçek OpenAI + gerçek Redis'e karşı manuel
doğrulama script'i.

Otomatik test değil — unit/entegrasyon testleri sahte (ücretsiz) sağlayıcılarla
cache mekaniğini zaten kanıtlıyor (bkz. tests/unit/test_cache.py,
tests/integration/test_cache.py). Burası GERÇEK OpenAI'a karşı çalışır,
çünkü bu branch'te bulunan gerçek hata (generate_recommendation()'ın
yanlışlıkla cache'lenmesi — bkz. docs/adr/0022) sahte sağlayıcılı testlerle
hiç yakalanamamıştı, sadece gerçek bir uçtan uca çalıştırmayla ortaya çıktı.
Amaç: cache katmanının HER senaryosunu (isabet/kaçırma, kısmi batch, model
izolasyonu, TTL süresi dolması, enabled=False, Redis'e ulaşılamama, ve asıl
bulunan hatanın kendisi) gerçek altyapıya karşı tek tek kanıtlamak.

Temizlik: bu script gerçek üretim sağlayıcılarını (openai/gpt-4o-mini,
openai/text-embedding-3-small) kullandığı için sahte bir isim/model öneki
YOK — script başlamadan önce ve tüm senaryolar bittikten sonra Redis'teki
`embed:openai:*`/`llm:openai:*` anahtarlarının bir "önce/sonra" farkı
alınır, SADECE bu çalıştırmada yeni oluşan anahtarlar silinir. Toptan bir
temizlik (flushdb, desen bazlı silme) YAPILMAZ — aksi halde gerçek
kullanıcı trafiğinin cache'ini de silebilirdi.

Kullanım:
    uv run python -m scripts.diagnostics.smoke_test_cache [etiket]
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path

import httpx
from redis.asyncio import Redis

from backend.db.redis import get_redis_client
from backend.main import app, lifespan
from backend.services.cache import CachedEmbeddingProvider, CachedLLMProvider
from backend.services.embedding import (
    EmbeddingProvider,
    OpenAIEmbedding,
    get_embedding_provider,
)
from backend.services.llm import ChatMessage, LLMProvider, OpenAILLM, get_llm_provider
from backend.services.rag.intent import parse_intent

logger = logging.getLogger(__name__)

RESULTS_DIR: Path = Path("evaluation/results/diagnostics/cache_smoke_test")
# Windows dosya sisteminde ":" geçersiz — diğer smoke test'lerdeki aynı format.
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"

_SHORT_TTL_SECONDS: int = (
    3  # TTL süresi dolma senaryosu için — gerçek TTL'ler (7/30 gün) beklenemez
)
_UNREACHABLE_REDIS_URL: str = "redis://localhost:9"  # 9 portu hiçbir zaman Redis olmaz
_CACHE_KEY_PATTERNS: tuple[str, ...] = ("embed:openai:*", "llm:openai:*")


def _record(name: str, description: str, passed: bool, **details: object) -> dict:
    """Her senaryo için tutarlı, zengin bir JSON kaydı üretir — terminale de yazdırır."""
    status = "GEÇTİ" if passed else "BAŞARISIZ"
    print(f"\n--- [{status}] {name} ---")
    print(f"  {description}")
    for key, value in details.items():
        display = str(value)
        if len(display) > 300:
            display = display[:300] + "…"
        print(f"  {key}: {display}")
    return {"name": name, "description": description, "passed": passed, **details}


async def _snapshot_cache_keys(redis_client: Redis) -> set[bytes]:
    """Script'in dokunduğu gerçek üretim namespace'lerindeki (openai/*)
    anahtarların anlık görüntüsünü alır — önce/sonra farkını almak için."""
    keys: set[bytes] = set()
    for pattern in _CACHE_KEY_PATTERNS:
        async for key in redis_client.scan_iter(match=pattern):
            keys.add(key)
    return keys


# --- Embedding senaryoları ---


async def _scenario_embedding_miss_then_hit(provider: CachedEmbeddingProvider) -> dict:
    text = "gerçek embedding cache testi — birebir isabet"

    t0 = time.perf_counter()
    first = await provider.embed_batch([text])
    t_miss = time.perf_counter() - t0

    t0 = time.perf_counter()
    second = await provider.embed_batch([text])
    t_hit = time.perf_counter() - t0

    passed = first == second and t_hit < t_miss / 2
    return _record(
        "embedding_miss_then_hit",
        "Aynı metin iki kez embed edilirse, ikinci çağrı gerçekten Redis'ten dönmeli (çok daha hızlı, aynı vektör).",
        passed,
        ilk_sure_sn=round(t_miss, 3),
        ikinci_sure_sn=round(t_hit, 3),
        vektor_boyutu=len(first[0]),
        vektorler_ayni=first == second,
    )


async def _scenario_embedding_partial_batch(provider: CachedEmbeddingProvider) -> dict:
    cached_text = "kısmi batch testi — önceden cache'lenmiş metin"
    new_text = "kısmi batch testi — yeni metin"

    await provider.embed_batch([cached_text])  # önceden cache'le

    t0 = time.perf_counter()
    result = await provider.embed_batch([cached_text, new_text])
    elapsed = time.perf_counter() - t0

    passed = len(result) == 2 and all(len(v) == provider.dimension for v in result)
    return _record(
        "embedding_partial_batch_hit",
        "İki metinlik bir batch'te biri zaten cache'liyse, sadece yeni metin için gerçek çağrı atılmalı (batch yine de eksiksiz dönmeli).",
        passed,
        sure_sn=round(elapsed, 3),
        sonuc_sayisi=len(result),
    )


async def _scenario_embedding_model_isolation(redis_client: Redis) -> dict:
    """Aynı REAL API'yi kullanan ama farklı `model` etiketine sahip iki
    sağlayıcı, aynı metin için cache'i PAYLAŞMAMALI."""

    class _RelabeledEmbedding(OpenAIEmbedding):
        """`embed_batch()` (miras alınan) gerçek API çağrısında hep GERÇEK
        `self._model`'i kullanır — sadece cache'in gördüğü `.model` etiketi
        değişir, gerçek istek etkilenmez."""

        @property
        def model(self) -> str:
            return f"{self._model}-simulasyon-v2"

    inner_a = OpenAIEmbedding()
    inner_b = _RelabeledEmbedding()
    provider_a = CachedEmbeddingProvider(
        inner_a, redis_client, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    provider_b = CachedEmbeddingProvider(
        inner_b, redis_client, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    text = "model izolasyonu testi — aynı metin"

    t0 = time.perf_counter()
    await provider_a.embed_batch([text])
    t_a = time.perf_counter() - t0

    t0 = time.perf_counter()
    await provider_b.embed_batch([text])
    t_b = time.perf_counter() - t0

    # İkisi de "ilk çağrı" gibi davranmalı (ikisi de yavaş, biri diğerinin cache'ini kullanmamalı)
    passed = t_a > 0.1 and t_b > 0.1
    return _record(
        "embedding_model_isolation",
        "Aynı metin, farklı `model` etiketli iki sağlayıcı arasında cache'i paylaşmamalı — ikisi de gerçek API'ye gitmeli.",
        passed,
        provider_a_sure_sn=round(t_a, 3),
        provider_b_sure_sn=round(t_b, 3),
    )


async def _scenario_embedding_disabled_bypass(redis_client: Redis) -> dict:
    inner = OpenAIEmbedding()
    provider = CachedEmbeddingProvider(
        inner, redis_client, enabled=False, ttl_seconds=_SHORT_TTL_SECONDS
    )
    text = "enabled=False testi — cache'e hiç yazılmamalı"

    t0 = time.perf_counter()
    await provider.embed_batch([text])
    t_first = time.perf_counter() - t0

    t0 = time.perf_counter()
    await provider.embed_batch([text])
    t_second = time.perf_counter() - t0

    key_exists = await redis_client.exists(provider._cache_key(text))  # type: ignore[attr-defined]
    passed = key_exists == 0 and t_second > t_first / 2
    return _record(
        "embedding_enabled_false_bypass",
        "enabled=False iken Redis'e hiç dokunulmamalı — iki çağrı da gerçek API'ye gitmeli, hiçbir anahtar oluşmamalı.",
        passed,
        ilk_sure_sn=round(t_first, 3),
        ikinci_sure_sn=round(t_second, 3),
        redis_anahtari_olustu_mu=bool(key_exists),
    )


async def _scenario_embedding_ttl_expiry(redis_client: Redis) -> dict:
    inner = OpenAIEmbedding()
    provider = CachedEmbeddingProvider(
        inner, redis_client, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    text = "TTL süresi dolma testi — embedding"

    await provider.embed_batch([text])
    key = provider._cache_key(text)  # type: ignore[attr-defined]
    ttl_before = await redis_client.ttl(key)

    await asyncio.sleep(_SHORT_TTL_SECONDS + 2)

    ttl_after = await redis_client.ttl(key)
    t0 = time.perf_counter()
    await provider.embed_batch(
        [text]
    )  # süresi dolduğu için bu da gerçek bir çağrı olmalı
    t_after_expiry = time.perf_counter() - t0

    passed = (
        0 < ttl_before <= _SHORT_TTL_SECONDS
        and ttl_after == -2
        and t_after_expiry > 0.1
    )
    return _record(
        "embedding_ttl_expiry",
        f"TTL={_SHORT_TTL_SECONDS}sn ile cache'lenen bir anahtar, süre dolunca gerçekten silinmeli (ttl()==-2) ve bir sonraki çağrı gerçek API'ye gitmeli.",
        passed,
        ttl_once_sn=ttl_before,
        ttl_suresi_dolduktan_sonra=ttl_after,
        suresi_dolduktan_sonraki_cagri_sn=round(t_after_expiry, 3),
    )


async def _scenario_embedding_redis_unreachable() -> dict:
    unreachable_redis = Redis.from_url(
        _UNREACHABLE_REDIS_URL, socket_connect_timeout=1, socket_timeout=1
    )
    inner = OpenAIEmbedding()
    provider = CachedEmbeddingProvider(
        inner, unreachable_redis, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    text = "Redis'e ulaşılamama testi"

    try:
        result = await provider.embed_batch([text])
        passed = len(result) == 1 and len(result[0]) == provider.dimension
        error = None
    except (
        Exception
    ) as e:  # noqa: BLE001 — bu senaryonun kendisi "hiç çökmemeli" iddiasını test ediyor
        passed = False
        error = str(e)
    finally:
        await unreachable_redis.aclose()

    return _record(
        "embedding_redis_unreachable_fallback",
        "Redis'e ulaşılamazsa istek ÇÖKMEMELİ — sessizce gerçek sağlayıcıya düşüp geçerli bir sonuç dönmeli.",
        passed,
        hata=error,
    )


# --- LLM senaryoları ---


async def _scenario_llm_miss_then_hit(provider: CachedLLMProvider) -> dict:
    messages = [
        ChatMessage(role="user", content="gerçek LLM cache testi — birebir isabet")
    ]

    t0 = time.perf_counter()
    first = await provider.complete(messages, temperature=0.0)
    t_miss = time.perf_counter() - t0

    t0 = time.perf_counter()
    second = await provider.complete(messages, temperature=0.0)
    t_hit = time.perf_counter() - t0

    passed = (
        first.from_cache is False
        and second.from_cache is True
        and second.content == first.content
        and second.total_tokens == 0
        and first.total_tokens > 0
        and t_hit < t_miss / 2
    )
    return _record(
        "llm_miss_then_hit_deterministic",
        "temperature=0.0 ile aynı mesaj iki kez gönderilirse, ikinci çağrı cache'ten dönmeli (from_cache=True, token=0, aynı içerik).",
        passed,
        ilk_sure_sn=round(t_miss, 3),
        ikinci_sure_sn=round(t_hit, 3),
        ilk_from_cache=first.from_cache,
        ikinci_from_cache=second.from_cache,
        ilk_token=first.total_tokens,
        ikinci_token=second.total_tokens,
    )


async def _scenario_llm_day_of_week_changes_cache_key(
    llm_provider: LLMProvider,
) -> dict:
    """search_intent.txt prompt'u today_weekday'i içine gömüyor — aynı ham
    sorgu, farklı `today` değerleriyle çağrılırsa render edilmiş prompt (ve
    dolayısıyla cache anahtarı) da değişmeli, ikinci çağrı da gerçek bir
    API çağrısı olmalı (bkz. docs/adr/0022)."""
    raw_query = "yarın uygun bir kuaför bul - gün testi"
    monday = date(2026, 8, 3)  # gerçekten bir pazartesi
    thursday = date(2026, 8, 6)  # gerçekten bir perşembe

    t0 = time.perf_counter()
    intent_monday, hit_monday = await parse_intent(llm_provider, raw_query, monday)
    t_monday = time.perf_counter() - t0

    t0 = time.perf_counter()
    intent_thursday, hit_thursday = await parse_intent(
        llm_provider, raw_query, thursday
    )
    t_thursday = time.perf_counter() - t0

    passed = hit_monday is False and hit_thursday is False and t_thursday > 0.1

    return _record(
        "llm_day_of_week_changes_cache_key",
        "Aynı ham sorgu, farklı `today` (gün) ile çağrılırsa render edilmiş prompt farklı olur — ikinci çağrı da cache miss olmalı (yanlış günün 'yarın' yorumu cache'den sızmamalı).",
        passed,
        pazartesi_from_cache=hit_monday,
        persembe_from_cache=hit_thursday,
        pazartesi_gun_of_week=intent_monday.day_of_week,
        persembe_gun_of_week=intent_thursday.day_of_week,
        pazartesi_sure_sn=round(t_monday, 3),
        persembe_sure_sn=round(t_thursday, 3),
    )


async def _scenario_llm_non_deterministic_never_cached(
    provider: CachedLLMProvider,
) -> dict:
    """ASIL BULUNAN HATANIN regresyon kanıtı (bkz. docs/adr/0022):
    generate_recommendation() (temperature=0.7) YANLIŞLIKLA cache'lenmişti,
    ikinci istek birebir aynı öneri metnini dönüyordu."""
    messages = [
        ChatMessage(
            role="user",
            content="İzmit'te uygun bir kuaför için 2-3 cümlelik doğal bir öneri metni yaz.",
        )
    ]

    first = await provider.complete(messages, temperature=0.7)
    second = await provider.complete(messages, temperature=0.7)

    passed = (
        first.from_cache is False
        and second.from_cache is False
        and first.content != second.content
    )
    return _record(
        "llm_non_deterministic_never_cached",
        "temperature=0.7 (örn. öneri üretimi) HİÇBİR ZAMAN cache'lenmemeli — iki çağrı da gerçek olmalı, içerik farklı çıkmalı (bu branch'te bulunup düzeltilen gerçek hatanın regresyon kanıtı).",
        passed,
        ilk_from_cache=first.from_cache,
        ikinci_from_cache=second.from_cache,
        icerikler_ayni_mi=first.content == second.content,
        ilk_metin=first.content,
        ikinci_metin=second.content,
    )


async def _scenario_llm_disabled_bypass(redis_client: Redis) -> dict:
    inner = OpenAILLM()
    provider = CachedLLMProvider(
        inner, redis_client, enabled=False, ttl_seconds=_SHORT_TTL_SECONDS
    )
    messages = [ChatMessage(role="user", content="enabled=False testi — LLM")]

    first = await provider.complete(messages, temperature=0.0)
    key = provider._cache_key(messages, 0.0, None, None)  # type: ignore[attr-defined]
    key_exists = await redis_client.exists(key)

    passed = first.from_cache is False and key_exists == 0
    return _record(
        "llm_enabled_false_bypass",
        "enabled=False iken temperature=0.0 olsa bile Redis'e hiç dokunulmamalı.",
        passed,
        from_cache=first.from_cache,
        redis_anahtari_olustu_mu=bool(key_exists),
    )


async def _scenario_llm_ttl_expiry(redis_client: Redis) -> dict:
    inner = OpenAILLM()
    provider = CachedLLMProvider(
        inner, redis_client, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    messages = [ChatMessage(role="user", content="TTL süresi dolma testi — LLM")]

    await provider.complete(messages, temperature=0.0)
    key = provider._cache_key(messages, 0.0, None, None)  # type: ignore[attr-defined]
    ttl_before = await redis_client.ttl(key)

    await asyncio.sleep(_SHORT_TTL_SECONDS + 2)

    ttl_after = await redis_client.ttl(key)
    second = await provider.complete(messages, temperature=0.0)

    passed = (
        0 < ttl_before <= _SHORT_TTL_SECONDS
        and ttl_after == -2
        and second.from_cache is False
    )
    return _record(
        "llm_ttl_expiry",
        f"TTL={_SHORT_TTL_SECONDS}sn ile cache'lenen bir LLM cevabı, süre dolunca gerçekten silinmeli, bir sonraki çağrı gerçek API'ye gitmeli.",
        passed,
        ttl_once_sn=ttl_before,
        ttl_suresi_dolduktan_sonra=ttl_after,
        ikinci_cagri_from_cache=second.from_cache,
    )


async def _scenario_llm_redis_unreachable() -> dict:
    unreachable_redis = Redis.from_url(
        _UNREACHABLE_REDIS_URL, socket_connect_timeout=1, socket_timeout=1
    )
    inner = OpenAILLM()
    provider = CachedLLMProvider(
        inner, unreachable_redis, enabled=True, ttl_seconds=_SHORT_TTL_SECONDS
    )
    messages = [ChatMessage(role="user", content="Redis'e ulaşılamama testi — LLM")]

    try:
        response = await provider.complete(messages, temperature=0.0)
        passed = bool(response.content) and response.from_cache is False
        error = None
    except (
        Exception
    ) as e:  # noqa: BLE001 — bu senaryonun kendisi "hiç çökmemeli" iddiasını test ediyor
        passed = False
        error = str(e)
    finally:
        await unreachable_redis.aclose()

    return _record(
        "llm_redis_unreachable_fallback",
        "Redis'e ulaşılamazsa istek ÇÖKMEMELİ — sessizce gerçek sağlayıcıya düşüp geçerli bir cevap dönmeli.",
        passed,
        hata=error,
    )


async def _scenario_full_recommend_pipeline(client: httpx.AsyncClient) -> dict:
    """Tam /recommend uçtan uca: ikinci istekte intent+embedding cache'den
    dönmeli (çok daha hızlı), ama öneri metni her seferinde taze üretilmeli
    (farklı olmalı) — tüm katmanların birlikte doğru çalıştığının kanıtı."""
    query = "İzmit'te ucuz bir dişçi öner - tam pipeline testi"

    t0 = time.perf_counter()
    r1 = await client.post("/recommend", json={"query": query, "user_id": 1})
    t_first = time.perf_counter() - t0

    t0 = time.perf_counter()
    r2 = await client.post("/recommend", json={"query": query, "user_id": 1})
    t_second = time.perf_counter() - t0

    body1, body2 = r1.json(), r2.json()
    passed = (
        r1.status_code == 200
        and r2.status_code == 200
        and body1["recommendation"] != body2["recommendation"]
    )
    return _record(
        "full_recommend_pipeline_twice",
        "Aynı sorguyla iki gerçek /recommend isteği: intent+embedding cache sayesinde ikinci istek daha hızlı olmalı, ama öneri metni HER SEFERİNDE taze (farklı) üretilmeli.",
        passed,
        ilk_sure_sn=round(t_first, 3),
        ikinci_sure_sn=round(t_second, 3),
        ilk_oneri=body1.get("recommendation"),
        ikinci_oneri=body2.get("recommendation"),
        oneri_metinleri_ayni_mi=body1["recommendation"] == body2["recommendation"],
    )


def _write_result(scenarios: list[dict], label: str | None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime(TIMESTAMP_FORMAT)
    filename = f"{label}_{timestamp}.json" if label else f"{timestamp}.json"
    output_path = RESULTS_DIR / filename
    passed_count = sum(1 for s in scenarios if s["passed"])
    payload = {
        "label": label,
        "timestamp": timestamp,
        "toplam_senaryo": len(scenarios),
        "gecen_senaryo": passed_count,
        "basarisiz_senaryo": len(scenarios) - passed_count,
        "scenarios": scenarios,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


async def main(label: str | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    scenarios: list[dict] = []

    # Tüm senaryolar TEK bir lifespan içinde çalışır — main.py'nin gerçek
    # startup/shutdown sırasını (BM25 kurulumu, Redis/LLM/reranker/DB
    # client'larının düzgün kapanışı) birebir kullanır, script kendi
    # kaynak yönetimini icat etmez.
    async with lifespan(app):
        redis_client = get_redis_client()
        llm_provider: LLMProvider = get_llm_provider()
        embedding_provider: EmbeddingProvider = get_embedding_provider()
        assert isinstance(embedding_provider, CachedEmbeddingProvider)
        assert isinstance(llm_provider, CachedLLMProvider)

        keys_before = await _snapshot_cache_keys(redis_client)

        scenarios.append(await _scenario_embedding_miss_then_hit(embedding_provider))
        scenarios.append(await _scenario_embedding_partial_batch(embedding_provider))
        scenarios.append(await _scenario_embedding_model_isolation(redis_client))
        scenarios.append(await _scenario_embedding_disabled_bypass(redis_client))
        scenarios.append(await _scenario_embedding_ttl_expiry(redis_client))
        scenarios.append(await _scenario_embedding_redis_unreachable())

        scenarios.append(await _scenario_llm_miss_then_hit(llm_provider))
        scenarios.append(
            await _scenario_llm_day_of_week_changes_cache_key(llm_provider)
        )
        scenarios.append(
            await _scenario_llm_non_deterministic_never_cached(llm_provider)
        )
        scenarios.append(await _scenario_llm_disabled_bypass(redis_client))
        scenarios.append(await _scenario_llm_ttl_expiry(redis_client))
        scenarios.append(await _scenario_llm_redis_unreachable())

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=30.0
        ) as client:
            scenarios.append(await _scenario_full_recommend_pipeline(client))

        keys_after = await _snapshot_cache_keys(redis_client)
        new_keys = keys_after - keys_before
        deleted = 0
        for key in new_keys:
            if await redis_client.delete(key):
                deleted += 1
        logger.info(
            "Temizlik: bu çalıştırmada oluşan %d/%d anahtar silindi.",
            deleted,
            len(new_keys),
        )

    output_path = _write_result(scenarios, label)
    passed_count = sum(1 for s in scenarios if s["passed"])
    print(f"\n=== SONUÇ: {passed_count}/{len(scenarios)} senaryo geçti ===")
    print(f"Kaydedildi: {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "label",
        nargs="?",
        default=None,
        help="Sonuç dosyasının adına eklenecek opsiyonel etiket",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(label=args.label))

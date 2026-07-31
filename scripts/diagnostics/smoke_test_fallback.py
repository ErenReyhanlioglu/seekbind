"""feature/fallback-mechanism için gerçek OpenAI + gerçek Ollama'ya karşı
manuel doğrulama script'i.

Otomatik test değil — unit testler (tests/unit/test_fallback.py) sahte
provider'larla fallback mantığını, entegrasyon testleri (tests/integration/test_fallback.py)
gerçek Ollama'yı zaten kanıtlıyor. Burası GERÇEK OpenAI'a karşı çalışır,
çünkü bu branch'in en kritik riski (qwen3:4b'nin `think:false`'u yok sayması,
bkz. docs/adr/0024, ollama/ollama#12234) sadece gerçek bir uçtan uca
`response_format=json_object` çağrısıyla ortaya çıkabilir — sahte provider'lı
testler bunu hiç yakalayamaz.

Kullanım:
    uv run python -m scripts.diagnostics.smoke_test_fallback [etiket]
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import date
from pathlib import Path

from redis.asyncio import Redis

from backend.db.redis import get_redis_client
from backend.main import app, lifespan
from backend.services.embedding import EmbeddingProvider, OllamaEmbedding, OpenAIEmbedding, get_embedding_provider
from backend.services.fallback import FallbackEmbeddingProvider, FallbackLLMProvider
from backend.services.llm import ChatMessage, LLMProvider, LLMServiceError, OllamaLLM, OpenAILLM, get_llm_provider
from backend.services.rag.intent import parse_intent

logger = logging.getLogger(__name__)

RESULTS_DIR: Path = Path("evaluation/results/diagnostics/fallback_smoke_test")
TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H-%M-%S"
_CACHE_KEY_PATTERNS: tuple[str, ...] = ("embed:openai:*", "llm:openai:*", "embed:ollama*", "llm:ollama:*")
_JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}


class _UnreachableOpenAILLM(OpenAILLM):
    """`OpenAILLM`'in aynısı ama gerçekte hiç dinlenmeyen bir porta bağlanır —
    "OpenAI ulaşılamaz" senaryosunu para harcamadan, gerçek bir bağlantı
    hatasıyla (APIConnectionError -> LLMServiceError) simüle eder."""

    def __init__(self) -> None:
        super().__init__()
        self._client.base_url = "http://localhost:1/v1"  # type: ignore[assignment]


class _UnreachableOpenAIEmbedding(OpenAIEmbedding):
    """`_UnreachableOpenAILLM` ile aynı gerekçe, embedding tarafı için."""

    def __init__(self) -> None:
        super().__init__()
        self._client.base_url = "http://localhost:1/v1"  # type: ignore[assignment]


def _record(name: str, description: str, passed: bool, **details: object) -> dict:
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
    keys: set[bytes] = set()
    for pattern in _CACHE_KEY_PATTERNS:
        async for key in redis_client.scan_iter(match=pattern):
            keys.add(key)
    return keys


# --- LLM senaryoları ---


async def _scenario_llm_full_stack_baseline(llm_provider: LLMProvider) -> dict:
    """Gerçek `get_llm_provider()` (Fallback+Cache ile sarılmış) — birincil
    (OpenAI) sağlıklıyken hiçbir fallback tetiklenmeden normal cevap dönmeli."""
    response = await llm_provider.complete(
        [ChatMessage(role="user", content="tek kelimeyle 'merhaba' de")], temperature=0.0
    )
    passed = response.provider == "openai" and bool(response.content)
    return _record(
        "llm_full_stack_baseline",
        "Birincil (OpenAI) sağlıklıyken gerçek get_llm_provider() üzerinden normal bir cevap dönmeli.",
        passed,
        provider=response.provider,
        icerik=response.content,
    )


async def _scenario_llm_forced_primary_failure_uses_real_ollama() -> dict:
    primary = _UnreachableOpenAILLM()
    secondary = OllamaLLM()
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    try:
        response = await provider.complete([ChatMessage(role="user", content="tek kelimeyle 'merhaba' de")])
        passed = response.provider == "ollama" and bool(response.content)
        error = None
    except Exception as e:  # noqa: BLE001 — bu senaryo "çökmemeli" iddiasını test ediyor
        passed = False
        error = str(e)
        response = None
    finally:
        await primary.close()
        await secondary.close()

    return _record(
        "llm_forced_primary_failure_uses_real_ollama",
        "Birincil gerçekten ulaşılamaz olduğunda gerçek Ollama devreye girmeli.",
        passed,
        provider=response.provider if response else None,
        hata=error,
    )


async def _scenario_llm_fallback_intent_parsing_produces_clean_json() -> dict:
    """En kritik senaryo: gerçek `qwen3:4b-instruct-2507`'e fallback yoluyla
    `response_format=json_object` ile gidildiğinde, thinking izi (bkz.
    ollama/ollama#12234) `content`'e karışmamalı — JSON temiz parse olmalı."""
    primary = _UnreachableOpenAILLM()
    secondary = OllamaLLM()
    provider = FallbackLLMProvider(primary, secondary, enabled=True)

    try:
        raw_response = await provider.complete(
            [ChatMessage(role="user", content='Sadece şu JSON\'u aynen döndür: {"tamam": true}')],
            temperature=0.0,
            response_format=_JSON_RESPONSE_FORMAT,
        )
        has_think_leak = "<think" in raw_response.content or "</think" in raw_response.content
        try:
            json.loads(raw_response.content)
            valid_json = True
        except json.JSONDecodeError:
            valid_json = False

        intent, _ = await parse_intent(provider, "İzmit'te ucuz bir dişçi istiyorum", date.today())
        intent_ok = bool(intent.semantic_query)

        passed = raw_response.provider == "ollama" and not has_think_leak and valid_json and intent_ok
        error = None
    except Exception as e:  # noqa: BLE001
        passed = False
        error = str(e)
        has_think_leak = valid_json = intent_ok = None
        raw_response = None
    finally:
        await primary.close()
        await secondary.close()

    return _record(
        "llm_fallback_intent_parsing_produces_clean_json",
        "Fallback yoluyla gerçek qwen3:4b-instruct-2507-q4_K_M'e giden response_format=json_object isteği temiz JSON dönmeli, thinking izi content'e karışmamalı, gerçek parse_intent() de başarılı olmalı.",
        passed,
        thinking_izi_sizdi_mi=has_think_leak,
        gecerli_json_mi=valid_json,
        intent_basarili_mi=intent_ok,
        ham_icerik=raw_response.content if raw_response else None,
        hata=error,
    )


async def _scenario_llm_enabled_false_kill_switch_propagates_raw_failure() -> dict:
    primary = _UnreachableOpenAILLM()
    secondary = OllamaLLM()
    provider = FallbackLLMProvider(primary, secondary, enabled=False)

    try:
        await provider.complete([ChatMessage(role="user", content="bu hiç ulaşmamalı")])
        passed = False
        error = None
    except LLMServiceError as e:
        passed = True
        error = str(e)
    finally:
        await primary.close()
        await secondary.close()

    return _record(
        "llm_enabled_false_kill_switch_propagates_raw_failure",
        "enabled=False iken birincil başarısız olursa fallback hiç denenmemeli, hata olduğu gibi dışarı sızmalı.",
        passed,
        hata=error,
    )


# --- Embedding senaryoları ---


async def _scenario_embedding_full_stack_baseline(embedding_provider: EmbeddingProvider) -> dict:
    [vector] = await embedding_provider.embed_batch(["gerçek embedding fallback baseline testi"])
    passed = embedding_provider.name == "openai" and len(vector) == 1536
    return _record(
        "embedding_full_stack_baseline",
        "Birincil (OpenAI) sağlıklıyken gerçek get_embedding_provider() üzerinden normal (1536 boyut) bir vektör dönmeli.",
        passed,
        saglayici_adi=embedding_provider.name,
        boyut=len(vector),
    )


async def _scenario_embedding_forced_primary_failure_uses_real_ollama() -> dict:
    primary = _UnreachableOpenAIEmbedding()
    secondary = OllamaEmbedding()
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=True)

    try:
        [vector] = await provider.embed_batch(["gerçek embedding fallback testi"])
        passed = provider.name == secondary.name and len(vector) == 1024
        error = None
    except Exception as e:  # noqa: BLE001
        passed = False
        error = str(e)
        vector = []
    finally:
        await primary.close()
        await secondary.close()

    return _record(
        "embedding_forced_primary_failure_uses_real_ollama",
        "Birincil gerçekten ulaşılamaz olduğunda gerçek Ollama devreye girmeli (1024 boyut, doğru .name).",
        passed,
        boyut=len(vector),
        hata=error,
    )


async def _scenario_embedding_enabled_false_kill_switch_propagates_raw_failure() -> dict:
    from backend.services.embedding import EmbeddingServiceError

    primary = _UnreachableOpenAIEmbedding()
    secondary = OllamaEmbedding()
    provider = FallbackEmbeddingProvider(primary, secondary, enabled=False)

    try:
        await provider.embed_batch(["bu hiç ulaşmamalı"])
        passed = False
        error = None
    except EmbeddingServiceError as e:
        passed = True
        error = str(e)
    finally:
        await primary.close()
        await secondary.close()

    return _record(
        "embedding_enabled_false_kill_switch_propagates_raw_failure",
        "enabled=False iken birincil başarısız olursa fallback hiç denenmemeli, hata olduğu gibi dışarı sızmalı.",
        passed,
        hata=error,
    )


async def _scenario_close_sequence_does_not_raise() -> dict:
    llm_provider = FallbackLLMProvider(OpenAILLM(), OllamaLLM(), enabled=True)
    embedding_provider = FallbackEmbeddingProvider(OpenAIEmbedding(), OllamaEmbedding(), enabled=True)

    try:
        await llm_provider.close()
        await embedding_provider.close()
        passed = True
        error = None
    except Exception as e:  # noqa: BLE001
        passed = False
        error = str(e)

    return _record(
        "close_sequence_does_not_raise",
        "Fallback wrapper'ların close()'u, hem birincil hem ikincil client'ı hatasız kapatmalı.",
        passed,
        hata=error,
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
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


async def main(label: str | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    scenarios: list[dict] = []

    async with lifespan(app):
        redis_client = get_redis_client()
        llm_provider = get_llm_provider()
        embedding_provider = get_embedding_provider()

        keys_before = await _snapshot_cache_keys(redis_client)

        scenarios.append(await _scenario_llm_full_stack_baseline(llm_provider))
        scenarios.append(await _scenario_llm_forced_primary_failure_uses_real_ollama())
        scenarios.append(await _scenario_llm_fallback_intent_parsing_produces_clean_json())
        scenarios.append(await _scenario_llm_enabled_false_kill_switch_propagates_raw_failure())

        scenarios.append(await _scenario_embedding_full_stack_baseline(embedding_provider))
        scenarios.append(await _scenario_embedding_forced_primary_failure_uses_real_ollama())
        scenarios.append(await _scenario_embedding_enabled_false_kill_switch_propagates_raw_failure())

        scenarios.append(await _scenario_close_sequence_does_not_raise())

        keys_after = await _snapshot_cache_keys(redis_client)
        new_keys = keys_after - keys_before
        deleted = 0
        for key in new_keys:
            if await redis_client.delete(key):
                deleted += 1
        logger.info("Temizlik: bu çalıştırmada oluşan %d/%d anahtar silindi.", deleted, len(new_keys))

    output_path = _write_result(scenarios, label)
    passed_count = sum(1 for s in scenarios if s["passed"])
    print(f"\n=== SONUÇ: {passed_count}/{len(scenarios)} senaryo geçti ===")
    print(f"Kaydedildi: {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label", nargs="?", default=None, help="Sonuç dosyasının adına eklenecek opsiyonel etiket")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(label=args.label))

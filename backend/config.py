"""Uygulama genelinde kullanılan ayarları .env dosyasından okur.

Tüm servisler (embedding, llm, db, monitoring vb.) bağlantı bilgilerini
buradaki Settings sınıfı üzerinden alır, hiçbir yerde URL/port/credential
hardcoded yazılmaz.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# LLM çağrılarında izin verilen maksimum bekleme süresi (saniye)
LLM_CALL_TIMEOUT_SECONDS: int = 30

# Dış LLM API'sine (OpenAI/Ollama) izin verilen maksimum eşzamanlı istek
# sayısı — sınırsız bırakılırsa soket tükenmesi / sağlayıcı rate limit'ine
# (429) çarpma riski var
LLM_MAX_CONCURRENT_CALLS: int = 5

# BM25 index'inin periyodik olarak taze olup olmadığının kontrol edileceği aralık (saniye)
BM25_REFRESH_INTERVAL_SECONDS: int = 3600

# Jina rerank API çağrısı için zaman aşımı (saniye) — arama <2s hedefindeyken
# LLM çağrı zaman aşımından (30s) daha sıkı tutulur, aksi halde tek başına
# reranker çağrısı tüm bütçeyi tüketebilir.
JINA_RERANK_TIMEOUT_SECONDS: int = 10

# Jina reranker modeli — v2-base-multilingual'dan daha yeni, daha iyi BEIR
# skoru ve yine çok dilli (bkz. docs/roadmap.md "Önemli kararlar")
JINA_RERANKER_MODEL: str = "jina-reranker-v3"

# Embedding cache TTL'i (saniye) — "deploy-kaynaklı" bir cache: aynı metnin
# aynı modeldeki embedding'i asla değişmez, TTL burada doğruluk için değil
# sadece Redis bellek yönetimi için var. Uzun tutulur (30 gün).
EMBEDDING_CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 30

# LLM completion cache TTL'i (saniye) — intent parsing gibi deterministik
# (temperature=0.0) çağrılar için, aynı gerekçeyle uzun tutulur (7 gün).
LLM_CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 7


class Settings(BaseSettings):
    """.env dosyasından okunan uygulama ayarları."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Uygulama
    app_env: str = "development"
    debug: bool = False

    # PostgreSQL
    database_url: str

    # Qdrant
    qdrant_url: str
    qdrant_collection_name: str

    # OpenAI
    openai_api_key: SecretStr
    openai_embedding_model: str
    openai_llm_model: str  # runtime aday — gpt-4o-mini (bkz. docs/adr/0008-llm-comparison-phase-4.md)
    openai_enrichment_llm_model: str  # veri zenginleştirme, ADR-0001 ile sabit — gpt-4.1-mini

    # Ollama (yerel sağlayıcı — fallback hedefi, bkz. docs/adr/0023-ablation-candidate-models.md)
    ollama_base_url: str
    ollama_embedding_model: str
    ollama_llm_model: str

    # Aktif LLM sağlayıcısı (bkz. docs/adr/0008-llm-comparison-phase-4.md)
    active_llm_provider: Literal["openai", "ollama"] = "openai"

    # Jina AI (reranker)
    jina_api_key: SecretStr

    # SerpAPI (veri toplama)
    serpapi_api_key: SecretStr

    # Langfuse
    langfuse_public_key: SecretStr
    langfuse_secret_key: SecretStr
    langfuse_host: str

    # Rate limiting
    rate_limit_per_minute: int = 60

    # LLM çağrı zaman aşımı
    llm_call_timeout_seconds: int = LLM_CALL_TIMEOUT_SECONDS

    # LLM çağrılarında eşzamanlı istek sınırı
    llm_max_concurrent_calls: int = LLM_MAX_CONCURRENT_CALLS

    # BM25 index yenileme aralığı
    bm25_refresh_interval_seconds: int = BM25_REFRESH_INTERVAL_SECONDS

    # Jina reranker
    jina_reranker_model: str = JINA_RERANKER_MODEL
    jina_rerank_timeout_seconds: int = JINA_RERANK_TIMEOUT_SECONDS

    # Redis (embedding + LLM completion cache)
    redis_url: str
    enable_cache: bool = True
    embedding_cache_ttl_seconds: int = EMBEDDING_CACHE_TTL_SECONDS
    llm_cache_ttl_seconds: int = LLM_CACHE_TTL_SECONDS

    # Sağlayıcılar arası fallback (OpenAI -> Ollama, bkz. docs/adr/0024-fallback-mechanism.md)
    enable_fallback: bool = True


@lru_cache
def get_settings() -> Settings:
    """Settings örneğini önbellekten döner, her seferinde .env'i yeniden okumaz."""
    # pydantic-settings alanları constructor argümanından değil .env'den
    # dolduruyor — Pyright bu runtime davranışını göremediği için tüm
    # zorunlu alanları eksik argüman sanıyor (bilinen bir stub kısıtlaması).
    return Settings()  # pyright: ignore[reportCallIssue]

"""Uygulama genelinde kullanılan ayarları .env dosyasından okur.

Tüm servisler (embedding, llm, db, monitoring vb.) bağlantı bilgilerini
buradaki Settings sınıfı üzerinden alır, hiçbir yerde URL/port/credential
hardcoded yazılmaz.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# LLM çağrılarında izin verilen maksimum bekleme süresi (saniye)
LLM_CALL_TIMEOUT_SECONDS: int = 30

# BM25 index'inin periyodik olarak taze olup olmadığının kontrol edileceği aralık (saniye)
BM25_REFRESH_INTERVAL_SECONDS: int = 3600

# Jina rerank API çağrısı için zaman aşımı (saniye) — arama <2s hedefindeyken
# LLM çağrı zaman aşımından (30s) daha sıkı tutulur, aksi halde tek başına
# reranker çağrısı tüm bütçeyi tüketebilir.
JINA_RERANK_TIMEOUT_SECONDS: int = 10

# Jina reranker modeli — v2-base-multilingual'dan daha yeni, daha iyi BEIR
# skoru ve yine çok dilli (bkz. docs/roadmap.md "Önemli kararlar")
JINA_RERANKER_MODEL: str = "jina-reranker-v3"


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
    openai_llm_model: str

    # Ollama (fallback)
    ollama_base_url: str
    ollama_embedding_model: str
    ollama_llm_model: str

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

    # BM25 index yenileme aralığı
    bm25_refresh_interval_seconds: int = BM25_REFRESH_INTERVAL_SECONDS

    # Jina reranker
    jina_reranker_model: str = JINA_RERANKER_MODEL
    jina_rerank_timeout_seconds: int = JINA_RERANK_TIMEOUT_SECONDS


@lru_cache
def get_settings() -> Settings:
    """Settings örneğini önbellekten döner, her seferinde .env'i yeniden okumaz."""
    # pydantic-settings alanları constructor argümanından değil .env'den
    # dolduruyor — Pyright bu runtime davranışını göremediği için tüm
    # zorunlu alanları eksik argüman sanıyor (bilinen bir stub kısıtlaması).
    return Settings()  # pyright: ignore[reportCallIssue]

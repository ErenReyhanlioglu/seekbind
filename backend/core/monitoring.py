"""Langfuse ile minimal LLM çağrı izleme.

Kapsam bilinçli olarak dar: sadece gerçek LLM çağrılarını izlenebilir hale
getirir (bkz. `backend.services.llm` — `langfuse.openai.AsyncOpenAI`
kullanır, bu sayede ayrı bir manuel trace/span kodu yazmaya gerek kalmaz).
Dashboard, yapılandırılmış metadata şemaları, maliyet takip UI'ı gibi daha
zengin entegrasyon `feature/langfuse-integration` branch'ine bırakıldı.
"""

import os
from functools import lru_cache

# langfuse paketi Langfuse sınıfını __all__ ile dışa vurmuyor (bkz.
# langfuse/__init__.py: sadece "from .client import Langfuse" + bir bastırma
# yorumu), bu yüzden Pylance "private import" sanıyor. Ama bu, kurulu v2.60.10'un kendi
# kaynak kodunun (client.py) hata mesajında referans verdiği, versiyon-uygun
# resmi kullanım şekli — https://langfuse.com/docs/sdk/python/low-level-sdk
# ("get_client()" o sayfadaki daha yeni v3+ API'si, bu projede kullanılmıyor
# çünkü self-hosted sunucu docker-compose.yml'de v2'ye sabitlenmiş).
from langfuse import Langfuse  # pyright: ignore[reportPrivateImportUsage]

from backend.config import get_settings


@lru_cache
def get_langfuse_client() -> Langfuse:
    """Langfuse client'ını önbellekten döner (pahalı client, singleton tutulur).

    `langfuse.openai.AsyncOpenAI` sarmalayıcısı (bkz. `backend.services.llm`)
    izleme için kendi iç `LangfuseSingleton`'ını kullanır — bu, açıkça
    geçirdiğimiz `Langfuse(...)` örneğinden habersizdir, sadece
    `os.environ`'daki `LANGFUSE_*` değişkenlerine bakar. pydantic-settings
    ise `.env` değerlerini `os.environ`'a yazmaz. Bu yüzden değerler burada
    açıkça `os.environ`'a da yazılır — Langfuse'un kendi dokümante ettiği
    "low-level SDK" kurulum deseni budur.
    """
    settings = get_settings()
    os.environ.setdefault(
        "LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key.get_secret_value()
    )
    os.environ.setdefault(
        "LANGFUSE_SECRET_KEY", settings.langfuse_secret_key.get_secret_value()
    )
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    return Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )

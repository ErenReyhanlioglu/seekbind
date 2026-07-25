"""Hybrid arama servisi.

Semantik (Qdrant/vektör) ve lexical (BM25) aramayı Reciprocal Rank
Fusion (RRF) ile birleştirir. Kesin filtreler (konum/gün/fiyat) Qdrant
payload filtering ile vektör aramasından önce uygulanır — bkz.
docs/roadmap.md "Önemli kararlar" bölümü.
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business

_TURKISH_UPPERCASE_MAP: dict[str, str] = {"İ": "i", "I": "ı"}
_NON_WORD_PATTERN: re.Pattern[str] = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_turkish_text(text: str) -> str:
    """BM25 için metni küçük harfe çevirir ve noktalamayı temizler.

    Python'un yerleşik .lower()'ı Türkçe İ/I çiftini yanlış çevirir
    (İ -> 'i̇' iki karakter, I -> 'i' değil 'ı'); bu yüzden bu iki
    karakter önce özel eşlenir, kalanı (Ğ/Ş/Ç/Ö/Ü dahil) standart
    .lower() zaten doğru çeviriyor.
    """
    for uppercase, lowercase in _TURKISH_UPPERCASE_MAP.items():
        text = text.replace(uppercase, lowercase)
    text = text.lower()
    return _NON_WORD_PATTERN.sub(" ", text)


def tokenize(text: str) -> list[str]:
    """Normalize edilmiş metni BM25 için token listesine böler."""
    return normalize_turkish_text(text).split()


def build_lexical_text(business: Business) -> str:
    """BM25 corpus'una girecek metni işletmenin alanlarından üretir.

    search_vector (Postgres full-text search) ile aynı alan setini
    (title+services+rich_description+keywords) kullanır — iki farklı
    lexical metin tanımı olmasın diye, bkz. scripts/seed_db.py.
    """
    parts = [
        business.title,
        " ".join(business.services),
        business.rich_description or "",
        " ".join(business.keywords),
    ]
    return " ".join(part for part in parts if part)


async def fetch_active_businesses(session: AsyncSession) -> list[Business]:
    """Aktif (is_active=true) tüm işletmeleri döner — BM25 corpus'u bunlardan kurulur."""
    result = await session.execute(select(Business).where(Business.is_active.is_(True)))
    return list(result.scalars().all())


def build_corpus(businesses: list[Business]) -> tuple[list[int], list[list[str]]]:
    """İşletme listesinden BM25 corpus'unu üretir.

    Döndürülen iki liste index bazında eşleşir: documents[i], business_ids[i]
    numaralı işletmenin tokenize edilmiş metnidir. BM25Okapi bu eşlemeyi
    korumadığı için (sadece sıralı skor döner), rank'ten business.id'ye
    geri dönmek için bu eşleme ayrıca tutulur.
    """
    business_ids = [business.id for business in businesses]
    documents = [tokenize(build_lexical_text(business)) for business in businesses]
    return business_ids, documents

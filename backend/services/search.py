"""Hybrid arama servisi.

Semantik (Qdrant/vektör) ve lexical (BM25) aramayı Reciprocal Rank
Fusion (RRF) ile birleştirir. Kesin filtreler (konum/gün/fiyat) Qdrant
payload filtering ile vektör aramasından önce uygulanır — bkz.
docs/roadmap.md "Önemli kararlar" bölümü.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from rank_bm25 import BM25Okapi
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Business

Fingerprint = tuple[int, datetime | None]
_EMPTY_FINGERPRINT: Fingerprint = (0, None)

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


async def compute_fingerprint(session: AsyncSession) -> Fingerprint:
    """Aktif işletme sayısı + en son güncelleme zamanını döner.

    Tüm satırları çekmeden (title/services/rich_description gibi ağır
    alanlar olmadan) 'veri değişti mi?' sorusuna ucuz bir cevap verir —
    BM25Index.refresh_if_stale bunu tam corpus yeniden kurmadan önce
    kontrol eder.
    """
    result = await session.execute(
        select(func.count(Business.id), func.max(Business.updated_at)).where(
            Business.is_active.is_(True)
        )
    )
    count, max_updated_at = result.one()
    return count, max_updated_at


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


@dataclass(frozen=True)
class _BM25Snapshot:
    """Tek seferde, atomik olarak değiştirilen tutarlı bir index anlık görüntüsü.

    Yeni index'i ayrı bir nesnede kurup en son tek bir referans atamasıyla
    (BM25Index._snapshot = yeni_snapshot) devreye almak için — bu sayede
    eşzamanlı bir arama isteği hiçbir zaman yarım kurulmuş bir index
    okumaz, ya tamamen eskisini ya da tamamen yenisini görür. Lock gerekmez,
    Python'da tek bir attribute ataması zaten atomiktir.
    """

    bm25: BM25Okapi | None
    business_ids: list[int]
    fingerprint: Fingerprint


class BM25Index:
    """Bellekte tutulan BM25 lexical arama index'i.

    Postgres'teki search_vector'ün aksine index bellekte olduğu için,
    veri değiştiğinde kendiliğinden güncellenmez — refresh_if_stale
    çağrılmadan tazeliği garanti edilmez.
    """

    def __init__(self) -> None:
        self._snapshot = _BM25Snapshot(bm25=None, business_ids=[], fingerprint=_EMPTY_FINGERPRINT)

    def build(self, businesses: list[Business], fingerprint: Fingerprint) -> None:
        """Verilen işletme listesinden index'i sıfırdan kurar."""
        business_ids, documents = build_corpus(businesses)
        bm25 = BM25Okapi(documents) if documents else None
        self._snapshot = _BM25Snapshot(bm25=bm25, business_ids=business_ids, fingerprint=fingerprint)

    async def refresh_if_stale(self, session: AsyncSession) -> bool:
        """Fingerprint değiştiyse index'i yeniden kurar, değiştiyse True döner.

        Önce ucuz fingerprint sorgusuyla 'değişti mi?' kontrol edilir,
        sadece değiştiyse tüm aktif işletmeler çekilip corpus yeniden kurulur.
        """
        current_fingerprint = await compute_fingerprint(session)
        if current_fingerprint == self._snapshot.fingerprint:
            return False
        businesses = await fetch_active_businesses(session)
        self.build(businesses, current_fingerprint)
        return True

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Sorguyu BM25 ile skorlar, (business_id, skor) çiftlerini azalan skora göre döner.

        DİKKAT: BM25 skoru negatif olabilir — klasik Okapi IDF formülü,
        bir terim korpüsün neredeyse tamamında geçtiğinde matematiksel
        olarak negatife düşer (bu "alakasız" anlamına gelmez, sadece
        "bu terim ayırt edici değil" demektir). Bu yüzden skora göre
        eşik/filtre uygulanmaz — sadece göreceli sıralama kullanılır,
        RRF birleştirmesi zaten mutlak skor değil rank'e bakar.
        """
        snapshot = self._snapshot
        if snapshot.bm25 is None:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = snapshot.bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(snapshot.business_ids, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return ranked[:top_k]


@lru_cache
def get_bm25_index() -> BM25Index:
    """BM25Index singleton'ını döner.

    İlk çağrıda boş kurulur; gerçek veriyle doldurmak için build() ya da
    refresh_if_stale() çağrılması gerekir (bkz. lifespan startup, Faz 4
    sonraki adım).
    """
    return BM25Index()

"""`resolve_price_threshold` + `coverage_stats` ile kategori fiyat sağlık kontrolü (problem #2, ADR-0027).

Gerçek veride doğrulandı: 27 kategoriden 24'ünde 75. persentil yöntemi
~%25 kapsamlı, sağlıklı bir "pahalı" alt kümesi üretiyor (persentil
tanımı gereği beklenen). 3 küçük kategoride (Göz Doktoru, Cilt Bakım
Merkezi, Noter) simetrik MIN_COUNT'un altına düşüyor — bu modül bunu
her kategori için otomatik tespit eder.

`resolve_price_threshold`'un kendisi (backend/services/rag/pricing.py)
tekrar kullanılıyor, ikinci bir kopyası yazılmıyor — ranking/relevance
motoru değil saf DB persentil hesabı olduğu için paket bağımsızlığı
ilkesini ihlal etmiyor (bkz. ADR-0027, "Paket bağımsızlığı" bölümü).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.rag.pricing import PricePreference, resolve_price_threshold
from scripts.ragas_testset.business_lookup import fetch_category_businesses
from scripts.ragas_testset.coverage_stats import SplitResult, evaluate_split


async def check_category(
    session: AsyncSession, category: str, preference: PricePreference
) -> SplitResult:
    """Bir kategoride verilen fiyat tercihinin (cheap/expensive) ne kadar işletmeyi kapsadığını ölçer."""
    businesses = await fetch_category_businesses(session, category)
    min_price, max_price = await resolve_price_threshold(session, category, preference)
    matched_count = sum(
        1
        for business in businesses
        if (max_price is None or business.price_min <= max_price)
        and (min_price is None or business.price_max >= min_price)
    )
    return evaluate_split(matched_count, len(businesses))

"""Arama sonuçlarından doğal dilde öneri metni üretme."""

from backend.api.schemas import ProviderResult
from backend.services.llm import ChatMessage, LLMProvider, LLMServiceError
from backend.services.rag.prompts import RECOMMENDATION_PROMPT_PATH, SYSTEM_PROMPT_PATH, load_prompt
from backend.services.search import RatingPreference

RECOMMENDATION_RESULT_LIMIT: int = 5  # öneri prompt'una en fazla bu kadar işletme konur (token/maliyet)
_RECOMMENDATION_TEMPERATURE: float = 0.7

# rating_preference yoksa sıra her zamanki gibi alaka (RRF/reranker) sırası.
_RELEVANCE_ORDER_CONTEXT: str = (
    "Sıra önemlidir (ilk işletme en iyi eşleşmedir), ama hiçbir işletmeye "
    "sayısal bir uygunluk puanı verilmemiştir — sırayı sanki bir puan "
    "varmış gibi açıklamaya çalışma, sadece sırayı dikkate al."
)
# rating_preference="high"/"low" iken sıra artık alaka değil, weighted_rating
# bazlı (bkz. ADR-0015, search.service._sort_by_rating) — LLM'e bunu açıkça
# söylemezsek "ilk işletme en iyi eşleşmedir" varsayımıyla devam ediyor ve
# düşük puanlı bir sonucu yüksekmiş gibi övüyor (gerçek smoke test'te
# gözlemlendi: "en kötü dişçi" sorgusuna en düşük puanlı 5 sonuç doğru
# döndü, ama öneri metni "genel olarak yüksek puanlara sahip" dedi).
_HIGH_RATING_ORDER_CONTEXT: str = (
    "Kullanıcı en yüksek puanlı/en iyi işletmeyi sordu, bu yüzden sonuçlar "
    "alaka sırası değil PUANA GÖRE (en yüksekten en düşüğe) sıralandı. İlk "
    "işletme bu sonuçlar içindeki en yüksek puanlıdır, bunu doğal bir dille "
    "yansıt."
)
_LOW_RATING_ORDER_CONTEXT: str = (
    "Kullanıcı en düşük puanlı/en kötü işletmeyi sordu, bu yüzden sonuçlar "
    "alaka sırası değil PUANA GÖRE (en düşükten en yükseğe) sıralandı. İlk "
    "işletme bu sonuçlar içindeki en düşük puanlıdır — bunu açıkça ve "
    "dürüstçe belirt; düşük bir puanı yüksekmiş gibi gösterme ya da "
    "çelişkili şekilde konuyu 'aslında en iyisini önereyim'e çevirme."
)


class RecommendationGenerationError(Exception):
    """Öneri metni LLM çağrısı başarısız olduğunda."""


def _resolve_ordering_context(rating_preference: RatingPreference | None) -> str:
    """Sonuç sırasının NEDEN olduğunu prompt'a açıklayan metni seçer."""
    if rating_preference == "high":
        return _HIGH_RATING_ORDER_CONTEXT
    if rating_preference == "low":
        return _LOW_RATING_ORDER_CONTEXT
    return _RELEVANCE_ORDER_CONTEXT


def _format_business_for_prompt(index: int, business: ProviderResult) -> str:
    """Tek bir işletmeyi öneri prompt'u için okunabilir metne çevirir.

    Ham JSON değil düz metin veriyoruz — LLM ham JSON alanlarını olduğu gibi
    tekrar etme eğiliminde olabiliyor, okunabilir metin daha doğal bir öneri
    yazmasını sağlıyor.
    """
    lines = [
        f"{index}. {business.title} ({business.type_normalized})",
        f"   Fiyat aralığı: {business.price_min}-{business.price_max} TL",
    ]
    if business.weighted_rating is not None:
        # Ham rating değil weighted_rating kullanılıyor — ADR-0004'teki
        # Bayesian düzeltme, az yorumlu işletmelerin yapay şekilde uç bir
        # puana sahip görünmesini önlüyor, bu yüzden daha güvenilir sinyal.
        lines.append(f"   Puan: {business.weighted_rating:.1f}/5")
    if business.services:
        lines.append(f"   Hizmetler: {', '.join(business.services)}")
    if business.rich_description:
        lines.append(f"   Açıklama: {business.rich_description}")
    return "\n".join(lines)


async def generate_recommendation(
    llm_provider: LLMProvider,
    raw_query: str,
    results: list[ProviderResult],
    rating_preference: RatingPreference | None = None,
) -> str:
    """Arama sonuçlarından doğal dilde bir öneri metni üretir.

    İlk `RECOMMENDATION_RESULT_LIMIT` sonucu kullanır (token/maliyet) —
    `response_format` YOK, bu serbest metin bir cevap. `rating_preference`
    verilmişse (ADR-0015), prompt'a sıranın alaka değil puan bazlı
    olduğunu açıklayan doğru bağlam eklenir.
    """
    top_results = results[:RECOMMENDATION_RESULT_LIMIT]
    businesses_text = "\n".join(
        _format_business_for_prompt(i, business) for i, business in enumerate(top_results, start=1)
    )
    system_content = load_prompt(SYSTEM_PROMPT_PATH)
    recommendation_instructions = load_prompt(RECOMMENDATION_PROMPT_PATH).format(
        query=raw_query,
        businesses=businesses_text,
        ordering_context=_resolve_ordering_context(rating_preference),
    )
    messages = [
        ChatMessage(role="system", content=system_content),
        ChatMessage(role="user", content=recommendation_instructions),
    ]

    try:
        response = await llm_provider.complete(messages, temperature=_RECOMMENDATION_TEMPERATURE)
    except LLMServiceError as e:
        raise RecommendationGenerationError("Öneri üretimi LLM çağrısı başarısız") from e
    return response.content

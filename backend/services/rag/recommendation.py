"""Arama sonuçlarından doğal dilde öneri metni üretme."""

from backend.api.schemas import ProviderResult
from backend.services.llm import ChatMessage, LLMProvider, LLMServiceError
from backend.services.rag.prompts import RECOMMENDATION_PROMPT_PATH, SYSTEM_PROMPT_PATH, load_prompt

RECOMMENDATION_RESULT_LIMIT: int = 5  # öneri prompt'una en fazla bu kadar işletme konur (token/maliyet)
_RECOMMENDATION_TEMPERATURE: float = 0.7


class RecommendationGenerationError(Exception):
    """Öneri metni LLM çağrısı başarısız olduğunda."""


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
    if business.services:
        lines.append(f"   Hizmetler: {', '.join(business.services)}")
    if business.rich_description:
        lines.append(f"   Açıklama: {business.rich_description}")
    return "\n".join(lines)


async def generate_recommendation(
    llm_provider: LLMProvider,
    raw_query: str,
    results: list[ProviderResult],
) -> str:
    """Arama sonuçlarından doğal dilde bir öneri metni üretir.

    İlk `RECOMMENDATION_RESULT_LIMIT` sonucu kullanır (token/maliyet) —
    `response_format` YOK, bu serbest metin bir cevap.
    """
    top_results = results[:RECOMMENDATION_RESULT_LIMIT]
    businesses_text = "\n".join(
        _format_business_for_prompt(i, business) for i, business in enumerate(top_results, start=1)
    )
    system_content = load_prompt(SYSTEM_PROMPT_PATH)
    recommendation_instructions = load_prompt(RECOMMENDATION_PROMPT_PATH).format(
        query=raw_query, businesses=businesses_text
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

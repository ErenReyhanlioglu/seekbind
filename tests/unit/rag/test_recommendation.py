"""backend/services/rag/recommendation.py için birim testler."""

import pytest

from backend.api.schemas import ProviderResult
from backend.services.llm import ChatMessage, LLMResponse, LLMServiceError
from backend.services.rag.recommendation import RecommendationGenerationError, generate_recommendation


class _FakeLLMProvider:
    """LLMProvider Protocol'üne uyan, elle yazılmış test double'ı."""

    name = "fake"

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        self._content = content
        self._error = error
        self.last_response_format: dict[str, str] | None = None
        self.last_messages: list[ChatMessage] | None = None
        self.last_langfuse_name: str | None = None
        self.last_langfuse_metadata: dict[str, object] | None = None

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        langfuse_name: str | None = None,
        langfuse_metadata: dict[str, object] | None = None,
    ) -> LLMResponse:
        self.last_response_format = response_format
        self.last_messages = messages
        self.last_langfuse_name = langfuse_name
        self.last_langfuse_metadata = langfuse_metadata
        if self._error is not None:
            raise self._error
        return LLMResponse(
            content=self._content,
            model="fake-model",
            provider="fake",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            finish_reason="stop",
        )

    async def close(self) -> None:
        pass


def _make_result(business_id: int, title: str = "Diş Kliniği Alfa", weighted_rating: float | None = 4.4) -> ProviderResult:
    return ProviderResult(
        id=business_id,
        title=title,
        type_normalized="Diş Kliniği",
        rating=4.5,
        weighted_rating=weighted_rating,
        price_min=100,
        price_max=300,
        address="İzmit",
        phone=None,
        online_available=False,
        gender="unisex",
        services=["kanal tedavisi"],
        tags=[],
        rich_description="Deneyimli diş hekimi.",
    )


async def test_generate_recommendation_returns_llm_text_on_success() -> None:
    provider = _FakeLLMProvider(content="Size en uygun diş kliniğini önerebilirim.")

    text = await generate_recommendation(provider, "ucuz dişçi", [_make_result(1)])

    assert text == "Size en uygun diş kliniğini önerebilirim."


async def test_generate_recommendation_sends_langfuse_name_and_metadata() -> None:
    """Bu adım Langfuse'ta 'recommendation_generation' adıyla ve sonuç
    sayısı/rating_preference gibi zengin metadata'yla görünmeli (bkz.
    feature/langfuse-integration)."""
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(
        provider, "en kötü dişçi", [_make_result(1), _make_result(2)], rating_preference="low"
    )

    assert provider.last_langfuse_name == "recommendation_generation"
    assert provider.last_langfuse_metadata == {"result_count": 2, "rating_preference": "low"}


async def test_generate_recommendation_does_not_request_json_response_format() -> None:
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "ucuz dişçi", [_make_result(1)])

    assert provider.last_response_format is None


async def test_generate_recommendation_raises_recommendation_generation_error_when_llm_fails() -> None:
    provider = _FakeLLMProvider(error=LLMServiceError("zaman aşımı"))

    with pytest.raises(RecommendationGenerationError):
        await generate_recommendation(provider, "ucuz dişçi", [_make_result(1)])


async def test_generate_recommendation_includes_weighted_rating_in_prompt() -> None:
    """weighted_rating (ADR-0004'ün Bayesian düzeltmesi) LLM'e gönderilen
    metne dahil edilmeli — az yorumlu işletmelerin uç puanlarını düzelten
    bu sinyal, ham `rating` yerine kullanılıyor."""
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "dişçi", [_make_result(1, weighted_rating=4.7)])

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "4.7/5" in user_message


async def test_generate_recommendation_omits_rating_line_when_weighted_rating_missing() -> None:
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "dişçi", [_make_result(1, weighted_rating=None)])

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "Puan:" not in user_message


async def test_generate_recommendation_uses_relevance_ordering_context_by_default() -> None:
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "dişçi", [_make_result(1)])

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "en iyi eşleşmedir" in user_message


async def test_generate_recommendation_uses_low_rating_ordering_context_when_preference_is_low() -> None:
    """ADR-0015: rating_preference="low" iken prompt, sıranın alaka değil
    puan bazlı olduğunu ve ilk işletmenin EN DÜŞÜK puanlı olduğunu açıkça
    belirtmeli — yoksa LLM "ilk = en iyi eşleşme" varsayımıyla düşük puanlı
    sonucu yüksekmiş gibi övüyor (gerçek smoke test'te gözlemlendi)."""
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "en kötü dişçi", [_make_result(1)], rating_preference="low")

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "en düşük puanlıdır" in user_message
    assert "en iyi eşleşmedir" not in user_message


async def test_generate_recommendation_uses_high_rating_ordering_context_when_preference_is_high() -> None:
    provider = _FakeLLMProvider(content="öneri metni")

    await generate_recommendation(provider, "en iyi dişçi", [_make_result(1)], rating_preference="high")

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "en yüksek puanlıdır" in user_message


async def test_generate_recommendation_limits_businesses_sent_to_prompt() -> None:
    provider = _FakeLLMProvider(content="öneri metni")
    results = [_make_result(i, title=f"İşletme {i}") for i in range(1, 10)]

    await generate_recommendation(provider, "dişçi", results)

    assert provider.last_messages is not None
    user_message = provider.last_messages[-1].content
    assert "İşletme 5" in user_message
    assert "İşletme 6" not in user_message

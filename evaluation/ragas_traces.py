"""RAG pipeline'ını gerçek DB/Qdrant/LLM'e karşı çalıştırıp ham trace toplama.

`evaluation/ragas_eval.py`'nin ilk aşaması — RAGAS skorlarının hesaplanacağı
(question, answer, contexts, reference) verisini üretir. `run_ragas_metrics()`
(bkz. `evaluation/ragas_metrics.py`) bu modülden bağımsız çalışabilsin diye
(kayıtlı bir trace dosyasından tekrar tekrar metrik hesaplanabilsin) ayrı
tutulur — pipeline'ı BAŞTAN çalıştırmak pahalı/yavaş, metrik hesaplama ucuz.
"""

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import DEMO_REFERENCE_TODAY
from backend.db.models import UserProfile
from backend.db.qdrant import get_qdrant_client
from backend.db.session import get_session_factory
from backend.services.embedding import EmbeddingProvider
from backend.services.llm import LLMProvider
from backend.services.rag import get_recommendation
from backend.services.rag.recommendation import (
    RECOMMENDATION_RESULT_LIMIT,
    _format_business_for_prompt,
)
from backend.services.search import BM25Index, get_reranker_provider

logger = logging.getLogger(__name__)

TEST_SET_PATH: Path = Path("evaluation/test_set.json")
EXPECTED_EMPTY_TAG: str = "expected_empty"


def load_questions() -> list[dict]:
    return json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))


def select_subset(questions: list[dict], limit: int | None) -> list[dict]:
    """Pilot testi için `limit` kadar, kategori/etiket çeşitliliğini koruyan
    eşit-aralıklı bir alt küme seçer; en az bir `expected_empty` soru dahil
    edilir (context'siz durumun da pilotta gözlemlenmesi için)."""
    if limit is None or limit >= len(questions):
        return questions
    step = len(questions) / limit
    indices = sorted({int(i * step) for i in range(limit)})
    subset = [questions[i] for i in indices]
    if not any(EXPECTED_EMPTY_TAG in q["intent_tags"] for q in subset):
        first_empty = next(
            q for q in questions if EXPECTED_EMPTY_TAG in q["intent_tags"]
        )
        subset[-1] = first_empty
    return subset


async def _collect_trace_for_question(
    session: AsyncSession,
    qdrant_client,
    bm25_index: BM25Index,
    embedding_provider: EmbeddingProvider,
    reranker_provider,
    llm_provider: LLMProvider,
    question: dict,
    today: date,
    user_id: int,
) -> dict:
    response = await get_recommendation(
        session=session,
        qdrant_client=qdrant_client,
        bm25_index=bm25_index,
        embedding_provider=embedding_provider,
        reranker_provider=reranker_provider,
        llm_provider=llm_provider,
        raw_query=question["question"],
        user_id=user_id,
        today=today,
    )
    # _format_business_for_prompt: generate_recommendation()'ın LLM'e GERÇEKTEN
    # gösterdiği metnin ta kendisi (backend/services/rag/recommendation.py) —
    # Faithfulness'ın kontrol edeceği "context" bu olmalı, ayrı bir formatlama
    # icat edilmedi.
    contexts = [
        _format_business_for_prompt(i, business)
        for i, business in enumerate(
            response.results[:RECOMMENDATION_RESULT_LIMIT], start=1
        )
    ]
    return {
        "id": question["id"],
        "question": question["question"],
        "category": question["category"],
        "intent_tags": question["intent_tags"],
        "answer": response.recommendation,
        "contexts": contexts,
        "reference": question["reference"],
    }


async def collect_traces(
    llm_provider: LLMProvider,
    embedding_provider: EmbeddingProvider,
    questions: list[dict],
) -> list[dict]:
    """Her soru için gerçek pipeline'ı çalıştırıp ham trace toplar.

    Sağlayıcıların kurulup kapatılması ÇAĞIRANIN sorumluluğu —
    `scripts/diagnostics/smoke_test_rag.py`'deki aynı sağlayıcı-sahiplik
    deseni (aynı kombinasyonla ardışık çağrıda "kapalı client" hatası
    almamak için).

    `today`, gerçek `date.today()` DEĞİL — `DEMO_REFERENCE_TODAY`
    (bkz. `backend/config.py`) kullanılır, çünkü `appointment_slots`
    seed anından itibaren sabit bir pencere için üretilmiş ve otomatik
    yenilenmiyor; gerçek bugünün tarihi kullanılsaydı gün/saat bazlı
    sorular seed penceresi eskidikçe sessizce boş context dönerdi.
    """
    today = DEMO_REFERENCE_TODAY
    qdrant_client = get_qdrant_client()
    reranker_provider = get_reranker_provider()
    session_factory = get_session_factory()
    bm25_index = BM25Index()

    traces: list[dict] = []
    try:
        async with session_factory() as session:
            await bm25_index.refresh_if_stale(session)
            user = (await session.execute(select(UserProfile))).scalars().first()
            if user is None:
                raise RuntimeError(
                    "UserProfile bulunamadı — önce "
                    "'uv run python -m scripts.seed_test_user' çalıştırılmalı"
                )
            for question in questions:
                trace = await _collect_trace_for_question(
                    session,
                    qdrant_client,
                    bm25_index,
                    embedding_provider,
                    reranker_provider,
                    llm_provider,
                    question,
                    today,
                    user.id,
                )
                traces.append(trace)
                logger.info("İşlendi: %s", question["id"])
    finally:
        await reranker_provider.close()
    return traces

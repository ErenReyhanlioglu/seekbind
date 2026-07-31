"""`tests/integration` paketinin ortak fixture'ları.

Bu paketteki testler gerçek dev Postgres/Qdrant'a karşı çalışır (docker-compose
servislerinin ayakta olması gerekir). Her test dosyası kendi başında
`pytestmark = pytest.mark.integration` tanımlar (bu satır bilerek conftest.py'de
DEĞİL — pytest'in `pytestmark` mekanizması sadece gerçek test modüllerinde
okunur, conftest.py'de tanımlansa sessizce hiçbir teste uygulanmaz) —
varsayılan `pytest` çalıştırmasında hariç tutulurlar (bkz. pyproject.toml
`addopts`), elle `pytest -m integration` ile çalıştırılırlar.

Üç bağımsız fixture grubu:
1. `api_client` — gerçek `lifespan()` (BM25 index kurulumu dahil) üzerinden
   ayağa kalkan, ASGI transport ile çalışan tek bir test client'ı.
2. `install_fake_recommend_providers` — LLM/embedding/reranker'ı Protocol'e
   uyan sahte sağlayıcılarla değiştirir (para/determinizm), sadece
   `/recommend` testlerinde kullanılır.
3. `savepoint_session` / `book_savepoint_client` — `/book` standart
   senaryoları için SAVEPOINT (nested transaction) izolasyonu.
4. `real_test_user_id` — `scripts/seed_test_user.py`'nin referans kullanıcısı,
   `near_me` testleri için gerçek koordinat kaynağı.
5. `query_counter` — `test/db-integration`'ın N+1 regresyon testleri için,
   gerçekten çalışan SQL sorgularını sayan bir liste.
"""

from collections.abc import AsyncGenerator, Callable, Generator

import httpx
import pytest
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import ExecutionContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.db.models import UserProfile
from backend.db.session import get_db_session, get_engine, get_session_factory
from backend.main import app, lifespan
from backend.services.embedding import get_embedding_provider
from backend.services.llm import ChatMessage, LLMResponse, get_llm_provider
from backend.services.search import get_reranker_provider
from scripts.seed_test_user import TEST_USER_NAME


@pytest.fixture(scope="session")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Gerçek uygulama `lifespan()`'iyle (BM25 index gerçek DB'den kurulur)
    ayağa kalkan, gerçek dev Postgres/Qdrant'a bağlanan tek bir test client'ı.

    `httpx.ASGITransport` gerçek bir soket/port açmadan, ama routing/
    `Depends()`/response şeması dahil tüm FastAPI akışından geçerek çalışır.
    Session-scoped: BM25 index kurulumu pahalı, testler arasında tekrar
    kurulmasına gerek yok (salt okuma endpoint'ler için güvenli).
    """
    async with lifespan(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Generator[None, None, None]:
    """Her testten sonra `app.dependency_overrides`'ı temizler.

    Testler kendi override'larını kendi içinde temizlese de, bir testin
    yarıda hata fırlatıp temizliği atlaması ihtimaline karşı ikinci bir
    güvence — sıradaki test yanlışlıkla önceki testin sahte sağlayıcısını
    ya da SAVEPOINT session'ını devralmasın.
    """
    yield
    app.dependency_overrides.clear()


class _FakeLLMProvider:
    """`LLMProvider` Protocol'üne uyan test double'ı.

    `langfuse_name`'e göre dallanır (`"intent_parsing"` -> sabit intent JSON,
    `"recommendation_generation"` -> sabit öneri metni) — tek bir HTTP
    isteğinde iki farklı LLM çağrısı olduğu için (bkz. rag/service.py),
    çağrı sırasına güvenmek yerine bu daha sağlam bir ayrım sinyali.
    """

    name = "fake"
    model = "fake-model"

    def __init__(self, intent_json: str, recommendation_text: str) -> None:
        self._intent_json = intent_json
        self._recommendation_text = recommendation_text

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
        content = self._intent_json if langfuse_name == "intent_parsing" else self._recommendation_text
        return LLMResponse(
            content=content,
            model="fake-model",
            provider="fake",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            finish_reason="stop",
        )

    async def close(self) -> None:
        pass


class _FakeEmbeddingProvider:
    """`EmbeddingProvider` Protocol'üne uyan test double'ı — sabit, ucuz bir vektör döner.

    `name = "openai"` BİLEREK gerçek sağlayıcı adıyla aynı: Qdrant collection
    adı `get_qdrant_collection_name()` ile bu isimden türetiliyor
    (`businesses_{name}`) — gerçek dev verisi `businesses_openai`
    collection'ında duruyor. `name`'i `"fake"` bırakırsak var olmayan
    `businesses_fake` collection'ına gidilir (404). Vektörün kendisi sahte
    olabilir (semantik olarak anlamsız sıralama üretir) ama hangi
    collection'a gidileceği gerçek olmalı — bu testlerin amacı zaten
    semantik kaliteyi değil, gerçek DB filtreleme + wiring'i kanıtlamak.
    """

    name = "openai"
    model = "fake-embedding-model"
    dimension = 1536

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]

    async def close(self) -> None:
        pass


class _IdentityRerankerProvider:
    """`RerankerProvider` Protocol'üne uyan test double'ı — sırayı değiştirmeden döner."""

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        return [(i, 1.0) for i in range(len(documents))]

    async def close(self) -> None:
        pass


@pytest.fixture
def install_fake_recommend_providers() -> Callable[[str, str], None]:
    """`/recommend` testlerine, LLM/embedding/reranker'ı sahte sağlayıcılarla
    değiştiren bir kurulum fonksiyonu verir.

    Sadece bu üçü override edilir — DB/Qdrant/BM25'e hiç dokunulmaz, gerçek
    dev altyapıya bağlı kalır (bkz. docs/roadmap.md kararı: `/recommend`
    salt okuma olduğu için gerçek veriye karşı test edilir). Temizlik
    `_clear_dependency_overrides` tarafından otomatik yapılır.
    """

    def _install(intent_json: str, recommendation_text: str = "Test önerisi.") -> None:
        app.dependency_overrides[get_llm_provider] = lambda: _FakeLLMProvider(intent_json, recommendation_text)
        app.dependency_overrides[get_embedding_provider] = lambda: _FakeEmbeddingProvider()
        app.dependency_overrides[get_reranker_provider] = lambda: _IdentityRerankerProvider()

    return _install


@pytest.fixture
async def savepoint_session() -> AsyncGenerator[AsyncSession, None]:
    """SAVEPOINT'e (nested transaction) bağlı bir session üretir.

    `get_db_session` (backend/db/session.py) başarılı istekte gerçekten
    `session.commit()` çağırıyor — bu yüzden düz "transaction aç, sonunda
    rollback et" yeterli değil, uygulama kodunun commit'i testin dışarıda
    tuttuğu transaction'ı erkenden gerçek DB'ye yazardı.

    `join_transaction_mode="create_savepoint"` (SQLAlchemy 2.0), bu deseni
    manuel bir `after_transaction_end` event listener'ı yazmadan çözüyor:
    uygulama kodunun her `commit()`'i sadece o anki SAVEPOINT'i kapatır,
    session otomatik olarak bir yenisini açar. Bu mekanizma gerçek dev DB'ye
    karşı elle doğrulandı (SAVEPOINT/RELEASE SAVEPOINT SQL logları, rollback
    sonrası sıfır iz).

    Test bitince `connection.rollback()` ile dış transaction (dolayısıyla
    içindeki tüm SAVEPOINT'ler) geri alınır, dev DB'de hiçbir iz kalmaz.
    """
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()


@pytest.fixture(scope="session")
async def real_test_user_id() -> int:
    """`scripts/seed_test_user.py`'nin oluşturduğu referans kullanıcının id'si.

    Gerçek koordinatlara sahip (bkz. `REFERENCE_LATITUDE`/`REFERENCE_LONGITUDE`
    o scriptte) — `near_me` testlerinde referans konum olarak kullanılır.
    `/recommend` salt okuma olduğu için bu paylaşılan kullanıcıyı okumak
    güvenli (bkz. proje kararı: `/book` testleri bu kullanıcıyı KULLANMIYOR,
    kendi throwaway satırlarını kuruyor — çünkü o testler yazma yapıyor).

    id her reseed'de değişebildiği için (bkz. o script'in docstring'i)
    isimle aranıyor, sabit bir sayı hardcode edilmiyor.
    """
    async with get_session_factory()() as session:
        result = await session.execute(select(UserProfile.id).where(UserProfile.name == TEST_USER_NAME))
        user_id = result.scalar_one_or_none()
    if user_id is None:
        pytest.skip(
            f"Referans test kullanıcısı ('{TEST_USER_NAME}') dev DB'de yok — "
            "scripts/seed_test_user.py çalıştırılmalı"
        )
    return user_id


@pytest.fixture
def book_savepoint_client(api_client: httpx.AsyncClient, savepoint_session: AsyncSession) -> httpx.AsyncClient:
    """`/book` standart senaryoları için `get_db_session`'ı SAVEPOINT'e bağlı
    session'a yönlendirir.

    Sadece bu fixture'ı kullanan testler etkilenir — `/health`/`/recommend`
    testleri `api_client`'ı doğrudan kullanır, gerçek `get_db_session`'a
    dokunulmaz. `test_book_concurrency.py` da bilerek bu fixture'ı DEĞİL,
    gerçek `get_db_session`'ı kullanır (bkz. o dosyanın docstring'i — race
    testinin bağımsız connection'lara ihtiyacı var).

    Override, `get_db_session`'ın commit-on-success/rollback-on-exception
    davranışını BİREBİR tekrarlıyor (yalnızca `yield` etmek yeterli değil) —
    SAVEPOINT deseninin asıl kanıtlamak istediği şey tam olarak bu: uygulama
    kodunun `commit()`'i gerçekten çağrılıyor, ama SAVEPOINT'i kapatmaktan
    öteye geçmiyor (dış transaction'a dokunmuyor).
    """

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield savepoint_session
            await savepoint_session.commit()
        except Exception:
            await savepoint_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = _override
    return api_client


@pytest.fixture
def query_counter() -> Generator[list[str], None, None]:
    """`engine.sync_engine`'e bağlanan, gerçekten çalışan SQL sorgularını
    sayan bir liste döner — `test_db_query_counts.py`'nin N+1 regresyon
    testleri için.

    `event.listen(engine, "before_cursor_execute", ...)` `AsyncEngine`'e
    doğrudan bağlanamaz (`NotImplementedError` fırlatır, `savepoint_session`'daki
    `session.sync_session` gotcha'sının aynı ailesi) — `engine.sync_engine`'e
    bağlanmak gerekiyor, gerçek dev DB'ye karşı doğrulandı.

    `SAVEPOINT`/`RELEASE SAVEPOINT`/`ROLLBACK TO SAVEPOINT` ifadeleri bilerek
    filtreleniyor: `savepoint_session` kullanan testlerde uygulama kodunun her
    `commit()`'i (`join_transaction_mode="create_savepoint"` sayesinde) bir
    SAVEPOINT açıp kapatıyor — bunlar test edilen fonksiyonun gerçek sorgu
    sayısıyla ilgisiz "muhasebe" ifadeleri, sayaca karışırsa sonuçlar
    (özellikle karşılaştırmalı küçük-N/büyük-N testlerinde) yanıltıcı olur.
    Bu filtreleme de gerçek dev DB'ye karşı elle doğrulandı.

    Kullanım: testte `query_counter.clear()` ile ölçüm öncesi sıfırlanır,
    fonksiyon çalıştırılır, `len(query_counter)` ile okunur.
    """
    engine = get_engine()
    statements: list[str] = []

    def _listener(
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: ExecutionContext | None,
        executemany: bool,
    ) -> None:
        normalized = statement.strip().upper()
        if not normalized.startswith(("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _listener)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _listener)

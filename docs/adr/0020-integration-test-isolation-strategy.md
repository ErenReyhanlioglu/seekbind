# ADR-0020: Entegrasyon testi izolasyon stratejisi — gerçek DB, SAVEPOINT ve sahte LLM sağlayıcıları

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-30

## Bağlam

`test/api-integration` (roadmap'te Faz 4'ün son maddesi), `/health`,
`/recommend`, `/book` endpoint'lerinin gerçek bir HTTP isteği üzerinden
hiç test edilmemiş olmasını kapatıyordu. Mevcut unit testler (`tests/unit/`,
%100 coverage) route fonksiyonlarını sahte `session`/`client` nesneleriyle
düz Python çağrısı gibi test ediyordu — gerçek FastAPI routing'i,
`Depends()` zincirinin gerçekten çözülmesini, Pydantic response şemasının
gerçek JSON üzerinden doğruluğunu ve HTTP status code döngüsünü hiçbir
test kanıtlamıyordu.

Asıl karar verilmesi gereken soru "nasıl test yazılır" değildi —
**entegrasyon testlerinde veritabanı izolasyonunu nasıl kuracağımız**
ve **hangi bağımlılığın gerçek, hangisinin sahte olacağı** idi. Bu ADR,
o kararları ve yol boyunca bulunan üç gerçek altyapısal hatayı kaydediyor.

## Değerlendirilen alternatifler

- **Tüm entegrasyon testleri için ayrı, küçük bir fixture veri seti**
  (5-10 elle kurulmuş işletme, ayrı bir Qdrant koleksiyonu). Reddedildi:
  `/recommend`'in BM25 index'i ve vektör araması gerçek embedding'lere
  ihtiyaç duyuyor — bu yolu seçersek o birkaç işletmeyi de OpenAI'la
  embed edip ayrı bir koleksiyona yüklememiz gerekirdi (ekstra maliyet +
  altyapı), üstelik test veri seti gerçek şemadan (kategori isimleri,
  fiyat dağılımı) sürekli sürüklenme riski taşırdı. Bunun yerine
  `/health`/`/recommend` (salt okuma oldukları için risksiz) doğrudan
  **mevcut dev Postgres + Qdrant'a** karşı çalıştırılıyor, assertion'lar
  exact-value değil **structural** (200 mü, şemaya uyuyor mu, sonuç
  boş/dolu mu) tutuluyor — dev veri zamanla değişebilir.
- **`/book` için ayrı bir test veritabanı/şeması + truncate-and-load.**
  Reddedildi: docker-compose'a yeni bir servis/şema eklemek, migration'ları
  oraya da uygulamak demek — bu ölçekte fazladan karmaşıklık. Bunun yerine
  SQLAlchemy'nin resmi "joining a session into an external transaction"
  deseni kullanıldı: `async_sessionmaker(bind=connection,
  join_transaction_mode="create_savepoint")`. Uygulama kodunun
  `get_db_session`'da gerçekten çağırdığı `session.commit()`, bu modda
  sadece o anki SAVEPOINT'i kapatıp otomatik yenisini açıyor — dış
  transaction'a hiç dokunmuyor. Test sonunda dış transaction'ın
  rollback edilmesiyle (SAVEPOINT'ler dahil) her şey geri alınıyor.
  Mekanizma gerçek dev DB'ye karşı elle doğrulandı: SQL loglarında her
  `commit()` sonrası otomatik yeni `SAVEPOINT` açıldığı, rollback
  sonrası **sıfır iz kaldığı** doğrudan sorguyla teyit edildi. `/book`
  testlerinin ihtiyaç duyduğu `Business`/`AppointmentSlot`/`UserProfile`
  satırları da mevcut dev veriye bağımlı kalınmadan, testin kendisi
  tarafından (aynı SAVEPOINT transaction'ı içinde) kuruluyor.
- **Race-condition testini de SAVEPOINT ile izole etmek.** Reddedildi —
  mekanik bir imkânsızlık, tercih meselesi değil: SAVEPOINT tek bir
  session/connection üzerinden çalışıyor, `asyncpg` aynı connection'da
  eşzamanlı sorguya izin vermiyor (ya hata verir ya sıralar) — yani
  "eşzamanlı" iki çağrı aslında aynı transaction'ın sıralı iki adımı
  olurdu, birbirleriyle hiç yarışmazdı. Bu yüzden `_claim_slot`'un
  (`backend/services/calendar.py` — atomik
  `UPDATE ... WHERE is_booked=false`) gerçekten eşzamanlı, BAĞIMSIZ
  connection'lar altında doğru davrandığını kanıtlamak için
  `test_book_concurrency.py` bilinçli olarak ayrı bir dosyada,
  override'sız gerçek `get_db_session` (her istek pool'dan kendi
  bağımsız connection'ını alır) + gerçek commit + kendi `try/finally`
  temizliğiyle çalışıyor. 2 yerine **10 eşzamanlı istek** kullanıldı —
  atomikliğin kanıtı matematiksel olarak 2 ile de yeterli olurdu, ama
  10 istek çakışma ihtimalini pratikte garantiye yaklaştırıp flake
  riskini azaltıyor.
- **LLM/embedding/reranker'a gerçek çağrı atmak.** Reddedildi — proje kod
  standartları açıkça yasaklıyor (maliyet + determinizm). `app.dependency_overrides`
  ile Protocol'e uyan sahte sağlayıcılar enjekte edildi; gerçek
  HTTP/routing/DI zinciri çalışıyor, zincirin ucundaki pahalı çağrı sahte.
  Sahte LLM'in intent JSON'u bilerek `price_preference` gibi alanlar
  içeriyor — sadece `semantic_query` dönseydi `resolve_price_threshold()`
  gibi DB'ye giden yan kodlar hiç tetiklenmezdi, sahte LLM'i en az test
  edilmiş (filtresiz) yoldan geçirmemek bilinçli bir tercih.

## Karar

1. **Veri stratejisi endpoint'in salt-okuma/yazma doğasına göre ayrıldı**
   (`/health`, `/recommend` → gerçek dev veri; `/book` → SAVEPOINT +
   testin kendi throwaway verisi; `/book` concurrency → gerçek commit +
   kendi temizliği). Tek bir kalıba sıkıştırılmadı.
2. **`tests/integration/conftest.py`** dört fixture grubu sağlıyor:
   `api_client` (gerçek `main.py::lifespan()` üzerinden ayağa kalkan,
   `httpx.ASGITransport` ile çalışan session-scoped client — BM25 index
   kurulumu pahalı olduğu için tekrar kurulmuyor),
   `install_fake_recommend_providers`, `savepoint_session`/
   `book_savepoint_client`, `real_test_user_id` (`scripts/seed_test_user.py`
   referans kullanıcısı, `near_me` testleri için).
3. **Tüm entegrasyon testleri `@pytest.mark.integration` ile opt-in** —
   `pyproject.toml`'da `addopts = "-m 'not integration'"`, düz `pytest`
   docker gerektirmeden hızlı kalıyor, `pytest -m integration` ile elle
   çalıştırılıyor. `pytestmark` bilerek `conftest.py`'de DEĞİL, her test
   dosyasının kendisinde (bkz. Sonuçlar'daki ilk hata).

## Sonuçlar

`pytest`: 223 unit + 10 yeni entegrasyon testi yeşil, `pyright`: proje
genelinde 0 hata. SAVEPOINT ve concurrency-cleanup mekanizmalarının dev
DB'de sıfır iz bıraktığı doğrudan sorguyla teyit edildi. Race-condition
testi 6 ayrı çalıştırmada hep tam olarak 1 kazanan üretti, flake
gözlenmedi.

**Bu branch'te bulunup düzeltilen üç altyapısal hata:**

- **`pytestmark`'ın `conftest.py`'de sessizce işe yaramaması.** pytest'in
  bu mekanizması sadece gerçek test modüllerinde okunuyor; `conftest.py`
  bir fixture/plugin dosyası olduğu için oraya konan `pytestmark` hiçbir
  teste uygulanmıyor. Marker her test dosyasının kendisine taşındı.
- **Session-scoped `api_client`, pytest-asyncio'nun varsayılan per-test
  event loop'uyla çakışıyordu.** `get_engine()` (`@lru_cache`) process
  boyunca tek bir gerçek `asyncpg` connection pool'u paylaşıyor — bu pool
  ilk hangi event loop'ta kurulduysa ona kilitleniyor. pytest-asyncio'nun
  varsayılanı (her test fonksiyonuna ayrı event loop) bu pool'u geçersiz
  kılıp `"attached to a different loop"` hatası veriyordu — hata mesajı
  `/health`'in Postgres'i "unhealthy" bulmasına yol açtı, ki DB'nin
  kendisiyle hiç ilgisi yoktu. `pyproject.toml`'a
  `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope
  = "session"` eklenerek çözüldü — unit testler mock kullandığı için
  (gerçek event loop'a duyarlı değiller) bu değişiklikten etkilenmedi,
  223'ü de yeniden doğrulandı.
- **Sahte embedding provider'ın `name`'i yanlış Qdrant collection'ına
  işaret ediyordu.** `get_qdrant_collection_name()` collection adını
  `businesses_{provider.name}` şeklinde türetiyor; sahte sağlayıcının
  adı `"fake"` bırakılınca var olmayan `businesses_fake` collection'ına
  gidilip 404 alınıyordu. Gerçek dev verisi `businesses_openai`'de
  duruyor — sahte provider'ın `name`'i bilerek `"openai"` yapıldı
  (vektörün kendisi sahte kalıyor, ama hangi collection'a gideceği gerçek
  olmak zorunda).

**Bilinen sınırlar** (bilerek kapsam dışı):
- `business_types` referans tablosu Alembic migration'larıyla değil
  sadece `scripts/seed_db.py` ile doluyor — entegrasyon testleri şu an
  "dev DB zaten seed'li" varsayımına dayanıyor, sıfırdan bir Postgres'e
  (örn. ileride CI) karşı çalıştırılırsa önce seed script'i gerekir.
- Sahte embedding provider'ın döndürdüğü vektör semantik olarak anlamsız
  (`[0.1, 0.1, ...]` sabit) — bu testler vektör aramasının *sıralama
  kalitesini* değil, gerçek DB filtreleme + wiring'in çalıştığını
  kanıtlıyor. Semantik kalite zaten `evaluation/` (RAGAS, Faz 6) ve
  `scripts/diagnostics/smoke_test_search.py`'nin kapsamında.
- Entegrasyon testleri henüz CI'a bağlı değil (`feature/ci-setup`,
  Faz 5) — şu an sadece geliştiricinin elle, docker ayakken çalıştırdığı
  bir opt-in suite.

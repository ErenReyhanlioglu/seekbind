# ADR-0026: CI pipeline kapsamı — lint, unit + kısmi entegrasyon, birleşik coverage gate'i, build

**Durum:** Kabul edildi
**Tarih:** 2026-08-01

## Bağlam

Roadmap'te Faz 5'in son maddesi `feature/ci-setup` — GitHub Actions ile
lint/test/build otomasyonu. Şu ana kadar `.github/workflows/` hiç yok,
`pyproject.toml`'da `ruff`/`black` tanımlı bile değil (sadece `pyright`
dev dependency olarak var).

Test tarafında zaten CI'ı bekleyen bir tasarım var: `tests/integration/`
`@pytest.mark.integration` ile opt-in (`addopts = "-m 'not integration'"`,
bkz. [ADR-0020](0020-integration-test-isolation-strategy.md)), ve o ADR'nin
"Bilinen sınırlar" bölümü bunun henüz CI'a bağlanmadığını açıkça not
düşmüştü. Ayrıca `pyproject.toml`'daki `requires_ollama` marker'ının
açıklaması da doğrudan *"feature/ci-setup bu testleri ayrıca ele
almalı"* diyor.

## Değerlendirilen alternatifler

**Entegrasyon testlerini CI'a hiç katmama.** İlk bakışta güvenli/basit
görünüyor ama gereksiz feragat: `tests/integration/factories.py`
sayesinde dosyaların çoğu (`test_db.py`, `test_db_query_counts.py`,
`test_book.py`, `test_book_concurrency.py`, `test_cache.py`,
`test_rate_limit.py`, `test_api.py`) kendi throwaway verisini üretiyor
ya da SAVEPOINT ile izole — gerçek üretim verisine bağımlı değiller ve
hiçbiri gerçek OpenAI/Jina/SerpAPI çağrısı yapmıyor. Bunları dışarıda
bırakmak, N+1 regresyonu (ADR-0021) gibi mock'la yakalanamayan hataları
CI'da kanıtlanmamış bırakırdı. Reddedildi.

**`test_recommend.py`'yi (near_me dahil) gerçek veriyle CI'da
çalıştırmak.** Bu dosyanın tamamı (5 testin 4'ü `len(results) > 0` gibi
assertion'lar içeriyor) gerçek dev Postgres + Qdrant'a (478 işletme,
`businesses_openai` collection'ı) bağımlı — LLM/embedding/reranker sahte
olsa da, sahte embedding provider'ın hangi Qdrant collection'ına
gideceği bilerek gerçek (bkz. ADR-0020). Bunu CI'da anlamlı kılmak için
iki yol var: (a) veri pipeline'ını (`fetch_serpapi` → `generate_synthetic`
→ `enrich_with_llm` → `seed_db` → `load_embeddings`) her çalıştırmada
yeniden üretmek — `enrich_with_llm`/`load_embeddings` gerçek OpenAI
çağrısı yapıyor, her push'ta gerçek para gider (bkz. proje bütçe kısıtı);
(b) dev DB/Qdrant'ın bir snapshot'ını alıp CI'da restore etmek — bu da
[ADR-0002](0002-raw-and-processed-data-excluded-from-git.md)'nin
ham/işlenmiş veriyi git dışında tutma kararıyla gerilim yaratır (git
dışı bir depolama + senkron tutma bakım yükü gerektirir). İkisi de bu
aşamada orantısız. Reddedildi — bkz. Karar.

**Coverage eşiğini sadece unit test job'una göre uygulamak.** Daha basit
(tek job, birleştirme gerekmez) ama yanıltıcı: unit testler mock
kullandığı için gerçek DB/Qdrant sorgu davranışını hiç kapsamıyor,
sayı gerçek kod kapsamını yansıtmazdı. Reddedildi.

**`scripts/`'i coverage ölçümüne dahil etmek.** `scripts/` CLAUDE.md'de
zaten `backend/`'den ayrı bir kategori (bilerek senkron, tek-seferlik
veri araçları). Bu script'lerin çoğu gerçek/ücretli API'ye gidiyor ve
zaten roadmap'te tek tek gerçek altyapıya karşı elle/diagnostic
script'lerle doğrulanmış durumda — mock'lu unit testle tekrar etmenin
katma değeri düşük. Ayrıca `tests/unit/` şu an `scripts/`'i hiç
hedeflemiyor, dahil edilirse gate ilk çalıştırmada backend kalitesiyle
ilgisi olmayan bir sebeple kırılırdı. Reddedildi.

## Karar

1. **Tetikleyici:** `push` (main hariç — main'e doğrudan push zaten
   GitHub branch protection ile kilitlenecek) + `pull_request`.

2. **Job'lar:**
   - `lint` — `black --check` + `ruff check` (CLAUDE.md'nin bu branch'e
     özel notu gereği `C901` siklomatik karmaşıklık kuralı dahil).
   - `unit-test` — düz `pytest` (zaten `addopts` ile integration hariç),
     altyapı gerektirmez.
   - `integration-test` — `services:` ile Postgres + Qdrant + Redis,
     `alembic upgrade head` (veri seed'i YOK), komut:
     `pytest -m "integration and not requires_ollama and not requires_seed_data"`.
   - `coverage-report` — `unit-test` ve `integration-test` job'larının
     coverage verisini (`coverage combine`) birleştirip `backend/`
     üzerinden `--cov-fail-under=90` uygular (`needs: [unit-test,
     integration-test]`).
   - `build` — `docker build -f docker/Dockerfile.backend .` doğrulaması.

3. **Yeni pytest marker: `requires_seed_data`.** `requires_ollama`
   deseninin aynısı — `test_recommend.py`'ye modül seviyesinde uygulanır
   (`pytestmark = [pytest.mark.integration, pytest.mark.requires_seed_data]`).
   CI'da bu iki marker da bilinçli olarak dışlanır.

4. **Config/secret ayrımı: `.env.ci`.** CI'da çalışan hiçbir test gerçek
   dış API'ye gitmiyor, ama `backend/config.py::Settings` tüm alanları
   zorunlu tutuyor ve `backend/main.py::lifespan()` kapanışta
   `get_llm_provider()`/`get_embedding_provider()`/`get_reranker_provider()`/
   `get_langfuse_client()`'ı **doğrudan** (test'lerin `dependency_overrides`'ından
   bağımsız olarak) çağırıp kapatıyor — yani bu client'ların inşa
   edilebilmesi için alanların dolu olması gerekiyor. Bunun için tamamen
   sahte/placeholder değerler içeren, git'e commit'lenebilir bir
   `.env.ci` dosyası eklendi (12-factor config pratiğiyle uyumlu — gerçek
   secret olmadığı için GitHub Secrets'a gerek yok, sadece
   `DATABASE_URL`/`QDRANT_URL`/`REDIS_URL` `services:` bloğundaki
   servislere işaret ediyor).

## Sonuçlar

- CI dışında bırakılanlar hâlâ opt-in, geliştiricinin elle çalıştırdığı
  testler olarak kalıyor:
  - `test_fallback.py` (`requires_ollama`) — native Ollama kurulumu
    gerektiriyor, CI runner'ında yok.
  - `test_recommend.py` (`requires_seed_data`, near_me dahil) — gerçek
    üretim ölçeğinde veri gerektiriyor, maliyet/karmaşıklık gerekçesiyle.
- Bu iki dışlama CI'da hiçbir regresyon koruması sağlamıyor — `/recommend`
  uçtan uca davranışı (near_me, price threshold, injection fallback vb.)
  sadece dev ortamında elle veya `scripts/diagnostics/smoke_test_rag.py`
  ile doğrulanmaya devam ediyor.
- CD (deploy otomasyonu) bu ADR'nin kapsamında değil — roadmap'te henüz
  bir faz olarak tanımlı değil, deploy edilecek bir ürün (frontend, Faz 7)
  olmadan anlamsız. Frontend tamamlandığında ayrı bir karar/ADR olarak
  ele alınacak.

## Bilinen sınır

`requires_seed_data` dışlaması kalıcı bir tasarım tercihi değil, mevcut
bütçe/altyapı kısıtı altında bir denge — ileride bir staging DB/Qdrant
snapshot mekanizması (ya da bütçe genişlerse gerçek pipeline'ın CI'da
çalıştırılması) kurulursa bu karar tekrar değerlendirilebilir.

## Güncelleme (2026-08-01): geçici altyapıya karşı gerçek doğrulamada bulunan 3 hata

Workflow yazıldıktan sonra, GitHub'a push etmeden önce, gerçek (ama izole/
geçici — dev docker-compose stack'ine dokunulmadan, farklı portlarda)
Postgres/Qdrant/Redis container'larına karşı `alembic upgrade head` +
`pytest -m "integration and not requires_ollama and not requires_seed_data"`
elle çalıştırıldı. Bu, tasarımın kağıt üzerinde doğru görünüp taze/boş bir
Postgres'e karşı gerçekten çalışmadığı üç noktayı ortaya çıkardı:

1. **`business_types` referans tablosu boş kalıyordu.** `businesses.type_normalized`
   bu tabloya FK ile bağlı, ama tablo Alembic migration'larıyla değil sadece
   `scripts/seed_db.py::seed_business_types()` ile doluyor — bu da zaten
   [ADR-0020](0020-integration-test-isolation-strategy.md)'nin "Bilinen
   sınırlar" bölümünde önceden işaretlenmişti. Throwaway işletme oluşturan
   her test (`test_book.py`, `test_book_concurrency.py`,
   `test_db_query_counts.py`) FK ihlaliyle başarısız oluyordu. Çözüm:
   `seed_business_types()` tamamen sabit, 27 satırlık, sıfır API maliyetli
   bir referans listesi (`scripts/constants/business_types.py`'den) —
   gerçek işletme verisiyle (478 kayıt, SerpAPI/OpenAI maliyeti) hiç ilgisi
   yok. `integration-test` job'una `alembic upgrade head`'den sonra, gerçek
   işletme verisi seed edilmeden, sadece bu fonksiyonu çağıran küçük bir
   adım eklendi.
2. **`test_db_query_counts.py`'nin 2 testi yanlışlıkla gerçek dev veriye
   bağımlıydı.** `_real_business_ids()` dev DB'den en az 50 var olan
   işletme okuyordu. Ama test edilen fonksiyonlar (`_fetch_businesses_by_id`,
   `fetch_available_business_ids`) düz birer `WHERE id IN (...)` sorgusu —
   ilişki yüklemesi yok, işletme içeriğine bakmıyor, sorgu sayısı
   ID'lerin gerçek/throwaway olmasından bağımsız (doğrudan kod okunarak
   doğrulandı). `_real_business_ids()`, aynı dosyadaki
   `test_book_appointment_alternative_search_query_count_independent_of_candidate_count`'ın
   zaten kullandığı throwaway-oluşturma desenine (`_create_throwaway_business_ids`)
   çevrildi — kanıtlanan şey (N+1 yok) değişmedi, sadece gereksiz dev-DB
   bağımlılığı kalktı.
3. **`test_db.py::test_appointment_slot_composite_index_is_used`** gerçekten
   büyük hacimli veriye muhtaç — kendi docstring'i zaten bunu söylüyordu
   ("gerçek dev veriye, 32k+ satır"). Bu, öncekilerden farklı bir sınıf:
   Postgres'in query planner'ı maliyet-bazlı çalışıyor, küçük/boş bir
   tabloda index kullanmayıp Seq Scan'e düşmek **hata değil doğru
   davranış** — throwaway birkaç satırla taklit edilemez. Bu tek test
   (dosyanın diğer testi değil) `requires_seed_data` ile işaretlenip
   `test_recommend.py` ile aynı kategoriye alındı.

Üçü de gerçek altyapıya karşı doğrulanarak düzeltildi — CI'da hâlâ
çalışacak entegrasyon testlerinin tamamı (business_types seed adımı dahil)
taze/boş bir Postgres'e karşı elle yeşil geçti.

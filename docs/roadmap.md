# Yol Haritası

Proje boyunca izlenen faz/branch planı. Her branch tek bir işi bitirip
`main`'e merge edilir, sonra silinir (bkz. `terminal_cheatsheet.md`).

Durum işaretleri: ✅ tamamlandı · ⏳ sırada · ⬜ planlı

---

## Faz 1 — Altyapı

- ✅ `feature/backend-config` — `config.py`, pydantic-settings ile env yönetimi
- ✅ `feature/docker-infra` — PostgreSQL + Qdrant + Langfuse (docker-compose)

## Faz 2 — Veri

- ✅ `feature/data-collection` — SerpAPI ile İzmit/Kocaeli işletme verisi çekme (`fetch_serpapi.py`), 478 gerçek işletme
- ✅ `feature/synthetic-data` — kural tabanlı zenginleştirme (`generate_synthetic.py`: tip, hizmet, fiyat, süre, online, cinsiyet, çalışma saati, slotlar, tags) + LLM ile açıklama/keyword (`enrich_with_llm.py`, batch mimarisi, `gpt-4.1-mini`)
- ✅ `feature/db-models` — SQLAlchemy modelleri, Alembic migration, `session.py` (şema tasarımı: `docs/database_schema.md`)
- ✅ `feature/db-seed` — işlenmiş veriyi Postgres'e yükleme (`seed_db.py`, bulk upsert + truncate-and-load)

## Faz 3 — Backend Çekirdek

- ✅ `feature/api-skeleton` — `main.py`, `routes.py`, `schemas.py`, health-check endpoint
- ✅ `feature/embedding-pipeline` — `embedding.py` servisi (Protocol ile soyutlanmış), `load_embeddings.py` ile 478 işletme Qdrant'a yüklendi (`businesses_openai`, 1536 boyut). Mode collapse kontrolü (`check_embedding_diversity.py`) doğrulandı: kategoriler-arası 0.42, kategori-içi 0.63-0.78 — sağlıklı ayrışma, risk yok

## Faz 4 — Arama & AI Pipeline

- ✅ `feature/search-service` — semantic + hybrid search (BM25 + vektör); kesin filtreler (konum/gün/fiyat) Qdrant payload filtering ile vektör aramasından önce uygulanacak. Bilinen küçük bir performans fırsatı (henüz yapılmadı): `search_providers()`'daki `vector_search()` ile `fetch_filtered_business_ids()` (ikisi de Qdrant çağrısı, birbirinin çıktısına bağımlı değil) şu an sıralı çalışıyor, `asyncio.gather` ile paralelleştirilebilir — acil değil, LLM çağrıları (1-3sn) yanında marjinal bir kazanım
- ✅ `feature/reranker` — cross-encoder reranking (Jina AI hosted rerank API, `jina-reranker-v3` — yerel bir model yerine, gerekçe [ADR-0013](adr/0013-reranker-provider-selection.md)'te)
- ✅ `feature/llm-service` — GPT-4o-mini/Qwen3 seçim mantığı (runtime); GPT-4o-mini bilinçli bir seçim — bütçe ve evaluator bağımsızlığı gerekçesiyle, bkz. [ADR-0008](adr/0008-llm-comparison-phase-4.md). Minimal Langfuse izleme (`core/monitoring.py` + `langfuse.openai` sarmalayıcı) bu branch'e dahil edildi — otomatik fallback yok, kapsam bilinçli olarak dar tutuldu. Qwen3 tarafındaki aday sonradan 4B'ye, Turkish-LLM adayı ise VRAM kısıtı nedeniyle listeden düşürüldü — bkz. [ADR-0023](adr/0023-ablation-candidate-models.md)
- ✅ `feature/rag-pipeline` — RAG orkestrasyon (intent parsing + öneri üretimi — projenin asıl LLM testi). `POST /recommend` endpoint'i eklendi. Fiyat eşiği LLM tahminine değil gerçek DB verisine dayanıyor, bkz. [ADR-0014](adr/0014-price-threshold-resolution.md). Konum (`NearFilter`/"yakınımda") o an ayrıştırılmıyordu (geocoding altyapısı yok, bilerek kapsam dışı, bkz. [ADR-0011](adr/0011-hard-filter-vs-semantic-separation.md)) — sonradan `ParsedIntent.near_me` ile (gerçek geocoding değil, `UserProfile` referans konumu ve bir sıralama sinyali olarak) kapatıldı, bkz. [ADR-0019](adr/0019-distance-as-ranking-signal.md). `scripts/diagnostics/smoke_test_rag.py` ile 16 senaryo (fiyat eşiği, veri penceresi dışı gün, bilinmeyen kategori, prompt injection, çoklu kategori vb.) gerçek DB/Qdrant/LLM'e karşı doğrulandı
- ✅ `feature/langfuse-integration` — trace gruplama (`@observe()`) + yapılandırılmış metadata, bkz. [ADR-0016](adr/0016-langfuse-trace-grouping.md). Tek bir `/recommend` isteğinin 2 LLM çağrısı (intent parsing + öneri üretimi) artık tek trace altında, ayrıştırılan filtreler/fallback bilgisi/sonuç sayısı metadata'da — gerçek Langfuse API'sinden doğrulandı. "Dashboard"/"maliyet takip UI'ı" Langfuse'ın kendi self-hosted arayüzü, ayrıca inşa edilmedi. Bilinen boşluk: `OllamaLLM` (Langfuse'dan bağımsız olarak) hâlâ gerçek bir Ollama sunucusuna karşı uçtan uca test edilmedi (bkz. ADR-0016)
- ✅ `feat/user-profile` — `user_profiles` + `bookings` tabloları (calendar-service'ten önce, referans veri olarak). `bookings`, `appointment_slots.is_booked`'ın yerine geçmiyor, sadece dolu bir slotun hangi kullanıcıya ait olduğunu etiketliyor — gerekçe `docs/database_schema.md`'de. `scripts/seed_test_user.py` bir referans test kullanıcısı (478 işletmenin ortalama konumunda) + farklı işletmelerden 5 gerçek dolu slotu ona bağlıyor, calendar-service'in çakışma kontrolünü ileride anlamlı test edebilmesi için
- ✅ `feature/calendar-service` — bkz. [ADR-0018](adr/0018-calendar-service-booking-and-alternatives.md). `POST /book`: belirli bir slotu kullanıcıya rezerve eder, kullanıcının kendi randevularıyla (farklı işletme dahil) çakışma kontrolü yapar. Müsait değilse (dolu ya da çakışma) yapılandırılmış alternatif önerisi döner — iki kaynaktan: aynı işletmenin başka zamanı (kronolojik) + aynı kategorideki, aynı gün müsait diğer işletmeler (`weighted_rating`'e göre sıralı, NULL'lar sona — ADR-0015 deseni). Çapraz-işletme araması `search/availability.py`'deki mevcut `fetch_available_business_ids()`'i yeniden kullanıyor — yeni bir arama motoru değil, `search_providers()`'ın kendi iki fazlı deseninin küçük ölçekli bir tekrarı. Mesafe o an bilinçli olarak dışarıda bırakılmıştı, sonradan aynı `apply_final_sort()` yeniden kullanılarak kapatıldı, bkz. [ADR-0019](adr/0019-distance-as-ranking-signal.md). Gerçek DB'ye karşı hem elle hem `scripts/diagnostics/smoke_test_calendar.py` ile (transaction rollback edilir, kalıcı iz bırakmaz) doğrulandı
- ✅ `test/api-integration` — `/health`, `/recommend`, `/book` için gerçek HTTP entegrasyon testleri (`tests/integration/`, `httpx.ASGITransport` + gerçek `lifespan()` — routing/`Depends()`/Pydantic response şeması dahil kanıtlandı). `/health` ve `/recommend` gerçek dev Postgres+Qdrant'a karşı (salt okuma, LLM/embedding/reranker `dependency_overrides` ile sahte — maliyet/determinizm); `/book` standart senaryoları SQLAlchemy'nin SAVEPOINT deseniyle (`join_transaction_mode="create_savepoint"`) izole edildi, dev DB'de sıfır iz kalmadığı doğrudan sorguyla teyit edildi; race-condition senaryosu (10 eşzamanlı istek) bilinçli olarak ayrı bir dosyada, gerçek commit + kendi temizliğiyle — SAVEPOINT tek connection'da gerçek eşzamanlılığı simüle edemediği için (bkz. [ADR-0020](adr/0020-integration-test-isolation-strategy.md)), 6 ayrı çalıştırmada flake gözlenmedi. **Faz 4 tamamlandı.**

**`feature/tool-calling` kaldırıldı** — gerekçe, 8 senaryoluk gerçek smoke
test kanıtı ve "SeekBind 2.0" notu için bkz. [ADR-0017](adr/0017-tool-calling-not-needed.md).

## Faz 5 — Dayanıklılık & Güvenlik

- ✅ `test/db-integration` — DB katmanının proje kod standartlarına uygunluğunu kanıtlayan entegrasyon testleri (`tests/integration/test_db.py`, `test_db_query_counts.py`). Kod tabanının tamamı okunarak N+1 riski taşıyan bir yer bulunmadı (her yerde açık join, lazy relationship traversal yok) — testler bunu regresyona karşı korumalı bir garantiye çevirdi: `query_counter` fixture'ı ile gerçek SQL sorgu sayısı, karşılaştırmalı (5 vs 50 veri boyutu) yöntemle O(1) olduğu kanıtlanarak ölçüldü. Ayrıca transaction rollback (`get_db_session`) ve index kullanımı (`EXPLAIN`, gerçek 32k+ satıra karşı) doğrudan test edildi — bkz. [ADR-0021](adr/0021-db-layer-standards-verification.md)
- ✅ `feature/cache-layer` — Redis destekli embedding + LLM completion (intent parsing) cache. `CachedEmbeddingProvider`/`CachedLLMProvider` Protocol'e uyan herhangi bir sağlayıcıyı sarabilen genel bir wrapper — cache anahtarı sağlayıcı adı + gerçek model adından türetiliyor. `generate_recommendation()` (temperature=0.7) bilinçli olarak kapsam dışı bırakıldı — ilk implementasyon bunu yanlışlıkla ihlal etmişti, gerçek OpenAI'a karşı elle doğrulanırken bulunup düzeltildi (sadece `temperature=0.0` cache'leniyor). Semantik cache bilinçli olarak "SeekBind 2.0" notuyla ertelendi. `scripts/diagnostics/smoke_test_cache.py` ile 13 senaryo (TTL süresinin gerçekten dolması, Redis'e ulaşılamama, gün-bazlı anahtar değişimi dahil) gerçek OpenAI/Redis'e karşı doğrulandı (13/13) — bkz. [ADR-0022](adr/0022-embedding-llm-cache-layer.md)
- ✅ `feature/fallback-mechanism` — OpenAI→Ollama otomatik fallback (LLM + embedding), `FallbackLLMProvider`/`FallbackEmbeddingProvider` — `CachedEmbeddingProvider`/`CachedLLMProvider` ile aynı Protocol-uyumlu wrapper deseni, `Fallback(Cache(primary), Cache(secondary))` sırasıyla (cache anahtarı hep gerçek sağlayıcıyı yansıtır). Embedding tarafı LLM'den farklı bir risk taşıyor (farklı sağlayıcının vektörü kıyaslanamaz bir uzayda) — `.name`/`.model`/`.dimension` bir `contextvars.ContextVar` ile task-scoped takip ediliyor (paylaşılan `@lru_cache`'li örnekte yarış durumunu önlemek için), toplu yüklemede (`load_embeddings.py`) fallback tamamen kapatılıyor. Gerçek altyapı testinde `qwen3:4b`'de bulunan bir Ollama hatası ([ollama/ollama#12234](https://github.com/ollama/ollama/issues/12234)) nedeniyle fallback hedefi `qwen3:4b-instruct-2507-q4_K_M`'e kesinleşti, bkz. [ADR-0024](adr/0024-fallback-mechanism.md). `scripts/diagnostics/smoke_test_fallback.py` ile 8 senaryo gerçek OpenAI+Ollama'ya karşı doğrulandı (8/8), embedding fallback collection'ı (`businesses_ollama-qwen3-embedding-0-6b`) gerçek 478 işletmeyle dolduruldu — operasyonel olarak da çalışır durumda
- ✅ `feature/middleware` — rate limiting (Redis destekli, IP bazlı, sabit pencere/fixed-window, `RateLimitMiddleware` her endpoint'i kapsıyor) + prompt injection filtresi (kalıp/anahtar-kelime bazlı, `detect_prompt_injection()` — gerçek ASGI middleware DEĞİL, `get_recommendation()`'ın en başında çağrılan düz bir fonksiyon). Tespit sonrası davranış hibrit: intent parsing için log+flag, öneri üretimi için `generate_recommendation()` hiç çağrılmadan var olan `RECOMMENDATION_FALLBACK_MESSAGE`'a atlanıyor — sert bir red değil, projenin "zarif bozulma" felsefesiyle tutarlı. Redis'e ulaşılamazsa rate limiting fail-open (bkz. `cache.py`'deki aynı felsefe). `scripts/diagnostics/smoke_test_prompt_injection.py` ile 16 kalıp kategorisi, hem gerçek `gpt-4o-mini` hem gerçek `qwen3:4b-instruct-2507-q4_K_M`'e karşı doğrulandı — ilk çalıştırmada gerçek bir hata bulundu (Türkçe İ/I normalizasyonu büyük harfle başlayan İngilizce kalıpları kırıyordu, `gpt-4o-mini`'de tam bir öneri metni sızmasına yol açtı), düzeltildi, ikinci çalıştırmada 16/16 (her iki LLM) geçti. Karar gerekçesi (kalıp filtre vs LLM-tabanlı sınıflandırma, gerçek ablasyon kanıtı) ve bulunan hatanın detayı için bkz. [ADR-0025](adr/0025-prompt-injection-detection-strategy.md)
- ✅ `feature/ci-setup` — GitHub Actions workflow: `lint` (black + ruff, `C901` siklomatik karmaşıklık dahil), `unit-test`, `integration-test` (throwaway/factory veri kullanan entegrasyon testleri — gerçek Postgres/Qdrant/Redis `services:` ile), `coverage-report` (unit + integration coverage'ı `coverage combine` ile birleştirip `backend/` üzerinden %90 eşik), `build` (`docker build` doğrulaması). `test_recommend.py` (near_me dahil, gerçek 478 işletme + Qdrant embedding verisine bağımlı) ve `test_db.py`'nin index-kullanım testi (gerçek büyük hacimli veriye muhtaç, Postgres planner davranışı) yeni `requires_seed_data` marker'ıyla, `test_fallback.py`'nin Ollama kısmı var olan `requires_ollama` marker'ıyla CI'da bilinçli olarak dışlandı — bkz. [ADR-0026](adr/0026-ci-pipeline-scope.md). `.env.ci` (tamamen sahte değerler, git'e commit'lenebilir) ile `Settings`'in zorunlu alan sorunu çözüldü. Gerçek (izole, geçici) altyapıya karşı elle doğrulanırken 3 gerçek hata bulunup düzeltildi: `business_types` referans tablosu migration'larla değil sadece `seed_db.py` ile doluyormuş (CI'a bu sabit/ücretsiz 27 satırı dolduran bir adım eklendi), `test_db_query_counts.py`'nin 2 testi yanlışlıkla gerçek dev veriye bağımlıydı (throwaway veriyle düzeltildi, kanıtlanan şey değişmedi), GitHub Actions'ın `$GITHUB_ENV` dosya komutu yorum satırlarını desteklemiyormuş (filtrelenerek düzeltildi). **Faz 5 tamamlandı.**

## Faz 6 — Değerlendirme

- ✅ `feature/ragas-testset` — 100 test sorusu hazırlama (`evaluation/test_set.json`)
- ✅ `feature/ragas-evaluation` — RAGAS (Faithfulness/Answer Relevancy/Context Precision/Context Recall, evaluator `gpt-4.1-mini` — bkz. [ADR-0009](adr/0009-ragas-evaluator-model.md)) + deterministik ID-bazlı metrikler (Top-1 accuracy, MRR, Recall@5, Precision@5, Hit Rate@5, pooled Context Precision, expected-empty accuracy — RAGAS'ın LLM-yargıcından bağımsız, `expected_business_ids` ile doğrudan ID karşılaştırması) ile 2×2 ablasyon (`gpt-4o-mini`/`qwen3:4b-instruct-2507-q4_K_M` × `text-embedding-3-small`/`qwen3-embedding:0.6b`, bkz. [ADR-0023](adr/0023-ablation-candidate-models.md)) 100 soru üzerinde tam olarak (kademeli değil) koşuldu. Sonuç: LLM seçimi embedding seçiminden çok daha belirleyici, `gpt-4o-mini` genel olarak önde — [ADR-0008](adr/0008-llm-comparison-phase-4.md)'in kararını ampirik olarak destekliyor. Tam tablo ve yorum için bkz. [docs/ragas_evaluation.md](ragas_evaluation.md). **Faz 6 tamamlandı.**

## Faz 7 — Frontend

- ⬜ `feature/frontend-mvp` — React arayüzü (backend stabil olduktan sonra)

---

## Roadmap dışı (ihtiyaç oldukça)

- ✅ `docs/terminal-cheatsheet` — git/uv/docker komut referansı
- ⬜ `perf/connection-pool-tuning` — `get_engine()` connection pool boyutu ayarı, tahminen `test/db-integration`'dan sonra

---

## Önemli kararlar (ileride "neden böyle yaptık" diye bakmak için)

Mimari kararlar artık `docs/adr/` altında ADR (Architecture Decision
Record) olarak tutuluyor — her karar kendi bağlamı, alternatifleri ve
sonuçlarıyla ayrı bir dosyada. Bkz. [docs/adr/README.md](adr/README.md).

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
- ✅ `feature/llm-service` — GPT-4o-mini/Qwen3/Turkish-LLM seçim mantığı (runtime); GPT-4o-mini bilinçli bir seçim — bütçe ve evaluator bağımsızlığı gerekçesiyle, bkz. [ADR-0008](adr/0008-llm-comparison-phase-4.md). Minimal Langfuse izleme (`core/monitoring.py` + `langfuse.openai` sarmalayıcı) bu branch'e dahil edildi — otomatik fallback yok, kapsam bilinçli olarak dar tutuldu
- ✅ `feature/rag-pipeline` — RAG orkestrasyon (intent parsing + öneri üretimi — projenin asıl LLM testi). `POST /recommend` endpoint'i eklendi. Fiyat eşiği LLM tahminine değil gerçek DB verisine dayanıyor, bkz. [ADR-0014](adr/0014-price-threshold-resolution.md). Konum (`NearFilter`/"yakınımda") o an ayrıştırılmıyordu (geocoding altyapısı yok, bilerek kapsam dışı, bkz. [ADR-0011](adr/0011-hard-filter-vs-semantic-separation.md)) — sonradan `ParsedIntent.near_me` ile (gerçek geocoding değil, `UserProfile` referans konumu ve bir sıralama sinyali olarak) kapatıldı, bkz. [ADR-0019](adr/0019-distance-as-ranking-signal.md). `scripts/diagnostics/smoke_test_rag.py` ile 16 senaryo (fiyat eşiği, veri penceresi dışı gün, bilinmeyen kategori, prompt injection, çoklu kategori vb.) gerçek DB/Qdrant/LLM'e karşı doğrulandı
- ✅ `feature/langfuse-integration` — trace gruplama (`@observe()`) + yapılandırılmış metadata, bkz. [ADR-0016](adr/0016-langfuse-trace-grouping.md). Tek bir `/recommend` isteğinin 2 LLM çağrısı (intent parsing + öneri üretimi) artık tek trace altında, ayrıştırılan filtreler/fallback bilgisi/sonuç sayısı metadata'da — gerçek Langfuse API'sinden doğrulandı. "Dashboard"/"maliyet takip UI'ı" Langfuse'ın kendi self-hosted arayüzü, ayrıca inşa edilmedi. Bilinen boşluk: `OllamaLLM` (Langfuse'dan bağımsız olarak) hâlâ gerçek bir Ollama sunucusuna karşı uçtan uca test edilmedi (bkz. ADR-0016)
- ✅ `feat/user-profile` — `user_profiles` + `bookings` tabloları (calendar-service'ten önce, referans veri olarak). `bookings`, `appointment_slots.is_booked`'ın yerine geçmiyor, sadece dolu bir slotun hangi kullanıcıya ait olduğunu etiketliyor — gerekçe `docs/database_schema.md`'de. `scripts/seed_test_user.py` bir referans test kullanıcısı (478 işletmenin ortalama konumunda) + farklı işletmelerden 5 gerçek dolu slotu ona bağlıyor, calendar-service'in çakışma kontrolünü ileride anlamlı test edebilmesi için
- ✅ `feature/calendar-service` — bkz. [ADR-0018](adr/0018-calendar-service-booking-and-alternatives.md). `POST /book`: belirli bir slotu kullanıcıya rezerve eder, kullanıcının kendi randevularıyla (farklı işletme dahil) çakışma kontrolü yapar. Müsait değilse (dolu ya da çakışma) yapılandırılmış alternatif önerisi döner — iki kaynaktan: aynı işletmenin başka zamanı (kronolojik) + aynı kategorideki, aynı gün müsait diğer işletmeler (`weighted_rating`'e göre sıralı, NULL'lar sona — ADR-0015 deseni). Çapraz-işletme araması `search/availability.py`'deki mevcut `fetch_available_business_ids()`'i yeniden kullanıyor — yeni bir arama motoru değil, `search_providers()`'ın kendi iki fazlı deseninin küçük ölçekli bir tekrarı. Mesafe o an bilinçli olarak dışarıda bırakılmıştı, sonradan aynı `apply_final_sort()` yeniden kullanılarak kapatıldı, bkz. [ADR-0019](adr/0019-distance-as-ranking-signal.md). Gerçek DB'ye karşı hem elle hem `scripts/diagnostics/smoke_test_calendar.py` ile (transaction rollback edilir, kalıcı iz bırakmaz) doğrulandı
- ✅ `test/api-integration` — `/health`, `/recommend`, `/book` için gerçek HTTP entegrasyon testleri (`tests/integration/`, `httpx.ASGITransport` + gerçek `lifespan()` — routing/`Depends()`/Pydantic response şeması dahil kanıtlandı). `/health` ve `/recommend` gerçek dev Postgres+Qdrant'a karşı (salt okuma, LLM/embedding/reranker `dependency_overrides` ile sahte — maliyet/determinizm); `/book` standart senaryoları SQLAlchemy'nin SAVEPOINT deseniyle (`join_transaction_mode="create_savepoint"`) izole edildi, dev DB'de sıfır iz kalmadığı doğrudan sorguyla teyit edildi; race-condition senaryosu (10 eşzamanlı istek) bilinçli olarak ayrı bir dosyada, gerçek commit + kendi temizliğiyle — SAVEPOINT tek connection'da gerçek eşzamanlılığı simüle edemediği için (bkz. [ADR-0020](adr/0020-integration-test-isolation-strategy.md)), 6 ayrı çalıştırmada flake gözlenmedi. **Faz 4 tamamlandı.**

**`feature/tool-calling` kaldırıldı** — gerekçe, 8 senaryoluk gerçek smoke
test kanıtı ve "SeekBind 2.0" notu için bkz. [ADR-0017](adr/0017-tool-calling-not-needed.md).

## Faz 5 — Dayanıklılık & Güvenlik

- ⬜ `test/db-integration` — `tests/integration/test_db.py`; gerçek Postgres'e karşı sorgu testleri (N+1 kontrolü dahil — unit testteki mock'lu session gerçek sorgu sayısını göremez). DB modelleri/migration'lar Faz 2'de tamamlandığı için blokajı yok, `ci-setup`'tan önce burada olması mantıklı — CI'ın container wiring'ine somut bir şey verir
- ⬜ `feature/cache-layer` — embedding/sonuç cache'leme
- ⬜ `feature/fallback-mechanism` — hata yönetimi + fallback zinciri
- ⬜ `feature/middleware` — rate limiting + prompt injection filtresi
- ⬜ `feature/ci-setup` — GitHub Actions workflow (lint, test, build) — backend servisleri yazılınca

## Faz 6 — Değerlendirme

- ⬜ `feature/ragas-testset` — 100 test sorusu hazırlama (`evaluation/test_set.json`)
- ⬜ `feature/ragas-evaluation` — RAGAS ile Faithfulness/Relevancy/Precision/Recall ölçümü; evaluator modeli ve ablasyon kapsamı (3x3 tam mı, kademeli mi) pilot teste bağlı, henüz kesinleşmedi — bkz. [ADR-0009](adr/0009-ragas-evaluator-model.md)

## Faz 7 — Frontend

- ⬜ `feature/frontend-mvp` — React arayüzü (backend stabil olduktan sonra)

---

## Roadmap dışı (ihtiyaç oldukça)

- ✅ `docs/terminal-cheatsheet` — git/uv/docker komut referansı

---

## Önemli kararlar (ileride "neden böyle yaptık" diye bakmak için)

Mimari kararlar artık `docs/adr/` altında ADR (Architecture Decision
Record) olarak tutuluyor — her karar kendi bağlamı, alternatifleri ve
sonuçlarıyla ayrı bir dosyada. Bkz. [docs/adr/README.md](adr/README.md).

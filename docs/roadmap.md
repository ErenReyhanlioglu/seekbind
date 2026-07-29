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
- ⏳ `feature/rag-pipeline` — RAG orkestrasyon (intent parsing + öneri üretimi — projenin asıl LLM testi)
- ⬜ `feature/langfuse-integration` — `feature/llm-service`'teki minimal izlemenin üzerine daha zengin entegrasyon (dashboard, yapılandırılmış metadata şemaları, maliyet takip UI'ı) — temel bağlantı zaten kuruldu. rag-pipeline'dan sonraya alındı: çok adımlı akış (intent parsing → arama → öneri) olmadan trace gruplama/metadata şeması tasarlamak erken olurdu, rag-pipeline'ın gerçek adımları netleşince yeniden yazmak riskliydi
- ⬜ `feature/calendar-service` — slot/çakışma kontrolü
- ⬜ `feature/tool-calling` — `tools.py` (calendar-service'i LLM'e tool olarak sunar)
- ⬜ `test/api-integration` — `tests/integration/test_api.py`; gerçek HTTP istekleriyle uçtan uca endpoint testleri (routing + `Depends()` + Pydantic response şeması + status code). `/health` dışında endpoint olmadığı için şu an yazılamaz — rag-pipeline/calendar-service/tool-calling'in hepsi bitip API yüzeyi tamamlanınca, Faz 4'ün kapanışı olarak buraya kondu

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

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
- ⏳ `feature/db-models` — SQLAlchemy modelleri, Alembic migration, `session.py`
- ⬜ `feature/db-seed` — işlenmiş veriyi Postgres'e yükleme (`seed_db.py`)

## Faz 3 — Backend Çekirdek

- ⬜ `feature/api-skeleton` — `main.py`, `routes.py`, `schemas.py`, health-check endpoint
- ⬜ `feature/embedding-pipeline` — `embedding.py` servisi + Qdrant'a yükleme (`load_embeddings.py`)

## Faz 4 — Arama & AI Pipeline

- ⬜ `feature/search-service` — semantic + hybrid search (BM25 + vektör)
- ⬜ `feature/reranker` — cross-encoder reranking
- ⬜ `feature/llm-service` — GPT-4o-mini/Qwen3/Turkish-LLM seçim mantığı (runtime)
- ⬜ `feature/langfuse-integration` — Langfuse SDK'sının backend'e bağlanması (`core/monitoring.py`) — docker-compose'da servis ayakta ama backend'e henüz hiç bağlanmadı
- ⬜ `feature/rag-pipeline` — RAG orkestrasyon (intent parsing + öneri üretimi — projenin asıl LLM testi)
- ⬜ `feature/tool-calling` — `tools.py`
- ⬜ `feature/calendar-service` — slot/çakışma kontrolü

## Faz 5 — Dayanıklılık & Güvenlik

- ⬜ `feature/cache-layer` — embedding/sonuç cache'leme
- ⬜ `feature/fallback-mechanism` — hata yönetimi + fallback zinciri
- ⬜ `feature/middleware` — rate limiting + prompt injection filtresi
- ⬜ `feature/ci-setup` — GitHub Actions workflow (lint, test, build) — backend servisleri yazılınca

## Faz 6 — Değerlendirme

- ⬜ `feature/ragas-testset` — 100 test sorusu hazırlama (`evaluation/test_set.json`)
- ⬜ `feature/ragas-evaluation` — RAGAS ile Faithfulness/Relevancy/Precision/Recall ölçümü

## Faz 7 — Frontend

- ⬜ `feature/frontend-mvp` — React arayüzü (backend stabil olduktan sonra)

---

## Roadmap dışı (ihtiyaç oldukça)

- ✅ `docs/terminal-cheatsheet` — git/uv/docker komut referansı

---

## Önemli kararlar (ileride "neden böyle yaptık" diye bakmak için)

- **LLM model seçimi:** Veri zenginleştirme ve runtime için `gpt-4.1-mini` (Luna/GPT-5.6 ailesi bu iş için overkill bulundu, maliyet/kalite dengesi mini'de)
- **`data/raw` ve `data/processed`** git'e commit'lenmiyor (`.gitignore`), sadece `.gitkeep` ile klasör yapısı korunuyor
- **`reviews_original`** SerpAPI'nin sayısal `reviews` alanından daha güvenilir (Türkçe "B" bin eki yanlış parse ediliyor)
- **`weighted_rating`** (Bayesian düzeltme) az yorumlu işletmelerin yanıltıcı şekilde öne çıkmasını engellemek için eklendi
- **`tags`** kural tabanlı (LLM değil) — sübjektif/kanıtsız nitelikler ("yaşlı dostu" gibi) bilerek üretilmiyor, halüsinasyon riski
- **`keywords`** (LLM tabanlı, `enrich_with_llm.py`) — `tags`'ten farklı olarak, işletmenin zaten sahip olduğu `services` listesinden türetiliyor (senonim/semptom bazlı arama terimleri), yeni bir öznitelik uydurmuyor
- **Embedding modeli karşılaştırması (Faz 3):** OpenAI `text-embedding-3-small` vs Türkçe'ye özel `embeddingmagibu-200m` vs `qwen3-embedding:0.6B` — hangisi Türkçe semantik aramada daha iyi performans veriyor karşılaştırılacak
- **LLM karşılaştırması (Faz 4):** `gpt-4.1-mini` vs `Qwen3 7B` vs `Turkish-LLM 7B` (Ollama üzerinden) — runtime kalite/maliyet kıyası
- **RAGAS evaluator modeli:** Tutarlılık için OpenAI kullanılacak (farklı modellerin çıktısı karşılaştırılırken değerlendiricinin sabit kalması önemli)
- **Hybrid search (Faz 4):** BM25 + semantic sonuçları Reciprocal Rank Fusion (RRF) ile birleştirilecek

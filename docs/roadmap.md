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

- ⬜ `feature/search-service` — semantic + hybrid search (BM25 + vektör); kesin filtreler (konum/gün/fiyat) Qdrant payload filtering ile vektör aramasından önce uygulanacak
- ⬜ `feature/reranker` — cross-encoder reranking (aday model: `bge-reranker-v2-m3` — hafif, çok dilli, LLM tabanlı reranker'dan daha hızlı)
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
- **Hard filter / semantic ayrımı (Faz 4):** "Salı sabahı İzmit'te ucuz dişçi" gibi bir sorguda kesin kısıtlar (gün, saat, konum, fiyat) vektör aramasına karıştırılmaz — LLM'den yapılandırılmış JSON çıktısı (gerçek Tool Calling API'si değil, `enrich_with_llm.py`'deki gibi `response_format=json_object`) ile önce ayrıştırılır, sadece anlamsal kısım ("ucuz dişçi") embedding aramasına gider. Kesin filtreler Qdrant'ın payload filtering'iyle uygulanır (arama alanını daraltır, hız+doğruluk kazandırır)
- **Sentetik açıklama homojenliği riski (mode collapse) — ✅ doğrulandı, risk yok.** LLM'ler yüksek olasılıklı kelimelere yönelme eğiliminde, bu da açıklamaların birbirine çok benzemesine yol açabilirdi. `enrich_with_llm.py`'deki önlemler (batch + "birbirine benzemesin" talimatı + `temperature=0.8` + işletme başına farklı girdi verisi) ölçüldü: 478 işletmenin gerçek embedding'lerinde kategoriler-arası ortalama benzerlik **0.42**, kategori-içi ortalama **0.63-0.78** arası (en yüksek: Sürücü Kursu — dar hizmet setine sahip olduğu için meşru, gerçek bir örtüşme). Hiçbir kategori 0.95 uyarı eşiğine yaklaşmadı, her kategori kategoriler-arası ortalamadan belirgin şekilde (0.21-0.36 fark) ayrışıyor. Sonuçlar `evaluation/results/diagnostics/embedding_diversity_businesses_openai.json`'da saklı (`scripts/check_embedding_diversity.py`)
- **Reranker model adayı (Faz 4):** `bge-reranker-v2-m3` — hafif, çok dilli (Türkçe dahil) cross-encoder, LLM tabanlı reranking'e göre çok daha düşük gecikme, `<2s` yanıt hedefi için uygun

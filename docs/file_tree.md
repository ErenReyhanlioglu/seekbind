```text
seekbind/
├── .env                          — API key'ler
├── .env.example                  — örnek env şablonu
├── .env.ci                       — CI için tamamen sahte değerler (git'e commit'lenebilir)
├── .gitignore                    — .env dahil
├── .github/
│   └── workflows/
│       └── ci.yml                — lint, unit-test, integration-test, coverage-report, build (bkz. ADR-0026)
├── .python-version               — uv için Python sürümü
├── CLAUDE.md                     — geliştirme kuralları (git-exclude ile gizli, yerelde tutulur)
├── pyproject.toml                — proje meta + bağımlılıklar
├── uv.lock                       — kilitli bağımlılık sürümleri
├── alembic.ini                   — Alembic yapılandırması
├── docker-compose.yml            — PG + Qdrant + Redis + Langfuse
├── docker-compose.prod.yml       — production overrides
├── LICENSE                       — MIT lisansı
├── README.md
│
├── alembic/                      — DB migration'ları
│   ├── README
│   ├── env.py                    — async migration ortamı
│   ├── script.py.mako            — migration şablonu
│   └── versions/
│       ├── 123e8e9f7bc4_...py    — ilk şema (business_types, businesses, appointment_slots)
│       └── 03e741412d25_...py    — user_profiles + bookings tabloları
│
├── docs/
│   ├── file_tree.md              — bu dosya
│   ├── tech_stack.md             — teknoloji listesi
│   ├── terminal_cheatsheet.md    — git/uv/docker komut referansı
│   ├── roadmap.md                — faz/branch planı
│   ├── database_schema.md        — ER diyagramı + tasarım kararları
│   ├── prompts.md                — backend/prompts/ dosyalarının indeksi
│   ├── ragas_evaluation.md       — RAGAS 2×2 ablasyon sonuçları
│   └── adr/                      — mimari kararlar (ADR), her karar kendi dosyasında
│       ├── README.md             — ADR indeksi + format açıklaması
│       └── 0000-...-0027-...md   — 28 numaralı ADR dosyası
│
├── data/
│   ├── raw/                      — SerpAPI ham çıktıları
│   └── processed/                — temizlenmiş + sentetik ekli
│
├── backend/
│   ├── main.py                   — FastAPI giriş noktası (lifespan: DB/Redis/HTTP client kapatma dahil)
│   ├── config.py                 — ayarlar (pydantic-settings), env okuma
│   │
│   ├── api/
│   │   ├── routes.py             — endpoint tanımları
│   │   └── schemas.py            — Pydantic modeller
│   │
│   ├── core/
│   │   └── monitoring.py         — Langfuse entegrasyonu (minimal izleme; `langfuse.openai` sarmalayıcı ile)
│   │
│   ├── services/
│   │   ├── embedding.py          — Protocol ile soyutlanmış embedding sağlayıcıları (OpenAI, Ollama)
│   │   ├── llm.py                — Protocol ile soyutlanmış LLM sağlayıcıları (OpenAI, Ollama — ADR-0008, ADR-0023, ADR-0024)
│   │   ├── cache.py               — Redis destekli embedding/LLM cache (ADR-0022)
│   │   ├── fallback.py            — OpenAI→Ollama otomatik fallback (ADR-0024)
│   │   ├── calendar.py            — slot + çakışma kontrolü (ADR-0018)
│   │   ├── user_location.py       — kullanıcı referans konumu çözümleme (near_me için)
│   │   ├── search/                — hybrid (semantic + lexical) arama, 300 satır kuralı için pakete bölündü
│   │   │   ├── __init__.py       — public re-export'lar (search_providers dahil)
│   │   │   ├── text.py           — Türkçe normalizasyon + tokenization
│   │   │   ├── bm25.py           — BM25Index (fingerprint tabanlı yenileme) + periyodik refresh loop
│   │   │   ├── vector.py         — Qdrant semantik arama (query_points, filtreli ID çekme)
│   │   │   ├── filters.py        — SearchFilters, Qdrant Filter çevirisi, mesafe hesaplama
│   │   │   ├── availability.py   — tarih/saat müsaitliği (appointment_slots'a karşı, iki fazlı filtrenin 2. fazı)
│   │   │   ├── fusion.py         — Reciprocal Rank Fusion (RRF)
│   │   │   ├── reranker.py       — cross-encoder reranking (Jina AI — ADR-0013)
│   │   │   └── service.py        — search_providers() orkestrasyonu
│   │   └── rag/                   — RAG orkestrasyonu, 300 satır kuralı için pakete bölündü
│   │       ├── __init__.py       — public re-export (get_recommendation)
│   │       ├── intent.py         — serbest metni yapılandırılmış filtrelere ayrıştırma (ADR-0011)
│   │       ├── pricing.py        — fiyat eşiği çözümleme (ADR-0014)
│   │       ├── prompts.py        — prompts/ dosyalarını __file__ göreceli okuyan load_prompt() yardımcısı
│   │       ├── recommendation.py — arama sonuçlarından doğal dilde öneri üretimi
│   │       └── service.py        — get_recommendation() orkestrasyonu (intent → arama → öneri, Langfuse trace'i)
│   │
│   ├── db/
│   │   ├── models.py             — SQLAlchemy modelleri
│   │   ├── session.py            — DB bağlantı yönetimi (engine, session factory)
│   │   ├── qdrant.py             — Qdrant client yönetimi (singleton)
│   │   └── redis.py              — Redis client yönetimi (singleton)
│   │
│   ├── prompts/
│   │   ├── system.txt                 — ana sistem promptu
│   │   ├── search_intent.txt          — intent çıkarma promptu
│   │   ├── recommendation.txt         — öneri üretme promptu
│   │   ├── fallback.txt               — kullanılmıyor (boş, ölü kod — bkz. docs/prompts.md)
│   │   └── synthetic_enrichment.txt   — enrich_with_llm.py için batch prompt'u
│   │
│   └── middleware/
│       ├── rate_limit.py         — Redis destekli, IP bazlı rate limiting
│       └── prompt_injection.py   — kalıp bazlı prompt injection tespiti (ADR-0025)
│
├── evaluation/
│   ├── test_set.json             — 100 test sorusu (ADR-0027 metodolojisiyle üretildi)
│   ├── ragas_traces.py           — pipeline'ı gerçek DB/Qdrant/LLM'e karşı çalıştırıp trace toplama
│   ├── ragas_metrics.py          — trace'lerden RAGAS'ın 4 metriğini hesaplama
│   ├── deterministic_metrics.py  — LLM-yargıçtan bağımsız, ID-bazlı deterministik metrikler
│   ├── ragas_eval.py             — CLI orkestrasyon (trace toplama + metrik hesaplama)
│   ├── service_keyword_tagging_log.md — service_keyword etiketleme sürecinin kaydı
│   └── results/
│       ├── ragas/                — RAGAS + deterministik metrik sonuçları, <llm>/<embedder>/ altında
│       └── diagnostics/          — RAGAS dışı veri/arama/pipeline kalite kontrolleri
│           │                        (scripts/diagnostics/ ile birebir eşleşir, her script kendi alt klasörüne yazar)
│           ├── embedding_diversity/
│           ├── search_smoke_test/
│           ├── rag_smoke_test/
│           ├── cache_smoke_test/
│           ├── calendar_smoke_test/
│           ├── fallback_smoke_test/
│           ├── prompt_injection_smoke_test/
│           ├── ranking_stage_diagnosis/  — reranker'ın hangi pipeline aşamasında sıralamayı bozduğunu bulan tanı
│           └── ragas_testset/            — test_set.json üretim sürecinin ara çıktıları
│
├── tests/
│   ├── unit/                     — backend/ paketleriyle birebir eşleşen alt klasörler (api/, db/, middleware/, rag/, search/, scripts/)
│   ├── integration/              — gerçek Postgres/Qdrant/Redis'e karşı (test_api.py, test_book.py, test_book_concurrency.py, test_cache.py, test_db.py, test_db_query_counts.py, test_fallback.py, test_rate_limit.py, test_recommend.py, factories.py, conftest.py)
│   └── conftest.py               — pytest fixtures
│
├── scripts/
│   ├── fetch_serpapi.py          — SerpAPI'den çek → data/raw/businesses.jsonl
│   ├── generate_synthetic.py     — orkestrasyon: temizlik + kural tabanlı
│   │                                alanlar (type, services, fiyat, süre,
│   │                                online, cinsiyet, saatler, slotlar, tags)
│   │                                → data/processed/businesses.jsonl
│   ├── enrich_with_llm.py        — batch'ler halinde LLM ile rich_description
│   │                                + keywords üretir → businesses_enriched.jsonl
│   │                                (kaynağın üzerine yazmaz, resume destekli)
│   ├── schemas.py                — ProcessedBusinessRecord ortak Pydantic şeması
│   ├── load_embeddings.py        — Qdrant'a veri yükleme (model başına ayrı collection)
│   ├── seed_db.py                — PostgreSQL seed
│   ├── seed_test_user.py         — referans test kullanıcısı + dolu slot seed'i
│   │
│   ├── constants/                — sentetik veri üretimi için sabit sözlükler
│   │   ├── business_types.py     — CATEGORIES, QUERY_TERM_TO_TYPE, get_type_to_category_group()
│   │   ├── service_taxonomy.py   — SERVICE_TAXONOMY (ağırlıklı)
│   │   ├── pricing.py            — PRICE_RANGES_TL, APPOINTMENT_DURATIONS_MIN
│   │   ├── attributes.py         — ONLINE_AVAILABLE, GENDER_PREFERENCE_WEIGHTS
│   │   └── working_hours.py      — WORKING_HOURS_TEMPLATE, jitter, hafta sonu olasılıkları
│   │
│   ├── synthetic/                — generate_synthetic.py'nin kural tabanlı yardımcıları
│   │   ├── ratings.py            — reviews_original parse, weighted_rating (Bayesian)
│   │   ├── selection.py          — hizmet/fiyat seçimi, cinsiyet stratified atama
│   │   ├── schedule.py           — çalışma saati jitter + slot üretimi
│   │   └── tags.py               — kural tabanlı tags (online, hafta sonu, puan, fiyat)
│   │
│   ├── ragas_testset/            — ADR-0027 metodolojisiyle test_set.json ground truth üretimi
│   │   ├── build_ground_truth.py — orkestrasyon
│   │   ├── ground_truth_filters.py / ground_truth_resolvers.py / predicates.py
│   │   ├── combination_search.py / search_combinations.py
│   │   ├── term_distinctiveness.py / scan_term_distinctiveness.py
│   │   ├── price_distinctiveness.py / scan_price_distinctiveness.py
│   │   ├── coverage_stats.py / existing_coverage.py
│   │   ├── business_lookup.py / turkish_lemma.py / reports.py
│   │
│   └── diagnostics/              — elle çalıştırılan, gözle değerlendirilen doğrulama script'leri
│       ├── _result_paths.py      — sonuç dosyalarının <deney>/<llm>/<embedder>/ klasörleme yardımcısı
│       ├── _run_provider_ablation.py — mini ablasyon koşum yardımcısı
│       ├── check_embedding_diversity.py — mode collapse kontrolü (kategori-içi/kategoriler-arası kosinüs benzerliği)
│       ├── diagnose_ranking_stages.py — BM25/vektör/RRF/reranker aşamalarında sıralama tanısı
│       ├── smoke_test_search.py  — search-service'i gerçek DB/Qdrant'a karşı doğrular
│       ├── smoke_test_rag.py     — RAG pipeline'ını (intent + öneri) gerçek DB/Qdrant/LLM'e karşı doğrular
│       ├── smoke_test_calendar.py — calendar-service'i gerçek DB'ye karşı doğrular
│       ├── smoke_test_cache.py   — embedding/LLM cache'ini gerçek Redis'e karşı doğrular
│       ├── smoke_test_fallback.py — OpenAI→Ollama fallback'ini gerçek altyapıya karşı doğrular
│       └── smoke_test_prompt_injection.py — prompt injection filtresini gerçek LLM'lere karşı doğrular
│
├── docker/
│   ├── Dockerfile.backend        — backend image
│   └── Dockerfile.frontend       — frontend image (henüz kullanılmıyor, frontend/ boş)
│
└── frontend/                     — React (21st.dev MCP ile üretilecek, henüz başlanmadı — Faz 7)
```

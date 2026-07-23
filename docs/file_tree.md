seekbind/
├── .env                          — API key'ler
├── .env.example                  — örnek env şablonu
├── .gitignore                    — .env dahil
├── requirements.txt              — bağımlılıklar
├── docker-compose.yml            — PG + Qdrant + Langfuse
├── docker-compose.prod.yml       — production overrides
├── LICENSE                       — MIT lisansı
├── README.md
│
├── docs/
│   ├── file_tree.md              — bu dosya
│   ├── tech_stack.md             — teknoloji listesi
│   └── terminal_cheatsheet.md    — git/uv/docker komut referansı
│
├── data/
│   ├── raw/                      — SerpAPI ham çıktıları
│   └── processed/                — temizlenmiş + sentetik ekli
│
├── backend/
│   ├── main.py                   — FastAPI giriş noktası
│   ├── config.py                 — ayarlar, env okuma
│   │
│   ├── api/
│   │   ├── routes.py             — endpoint tanımları
│   │   └── schemas.py            — Pydantic modeller
│   │
│   ├── core/
│   │   └── monitoring.py         — Langfuse entegrasyonu
│   │
│   ├── services/
│   │   ├── embedding.py          — OpenAI + Ollama embedding yönetimi
│   │   ├── llm.py                — GPT-4o-mini / Qwen3 / Turkish-LLM seçimi
│   │   ├── tools.py              — tool calling fonksiyonları
│   │   ├── search.py             — semantic + hybrid search
│   │   ├── rag.py                — RAG pipeline
│   │   ├── reranker.py           — cross-encoder reranking
│   │   ├── calendar.py           — slot + çakışma kontrolü
│   │   ├── cache.py              — caching katmanı
│   │   └── fallback.py           — hata yönetimi + fallback
│   │
│   ├── db/
│   │   ├── models.py             — SQLAlchemy modelleri
│   │   ├── session.py            — DB bağlantı yönetimi
│   │   └── seed.py               — mock veri yükleme
│   │
│   ├── prompts/
│   │   ├── system.txt            — ana sistem promptu
│   │   ├── search_intent.txt     — intent çıkarma promptu
│   │   ├── recommendation.txt    — öneri üretme promptu
│   │   └── fallback.txt          — fallback mesaj promptu
│   │
│   └── middleware/
│       ├── rate_limit.py         — rate limiting
│       └── prompt_injection.py   — güvenlik filtresi
│
├── evaluation/
│   ├── test_set.json             — 100 test sorusu
│   ├── ragas_eval.py             — RAGAS değerlendirme
│   └── results/                  — değerlendirme sonuçları
│       ├── semantic_only.json
│       ├── hybrid.json
│       └── hybrid_rerank.json
│
├── tests/
│   ├── unit/
│   │   ├── test_search.py        — arama servisi testleri
│   │   ├── test_rag.py           — RAG servisi testleri
│   │   ├── test_calendar.py      — takvim servisi testleri
│   │   ├── test_reranker.py      — reranker testleri
│   │   ├── test_embedding.py     — embedding model testleri
│   │   ├── test_llm.py           — LLM seçim testleri
│   │   └── test_tools.py         — tool calling testleri
│   ├── integration/
│   │   ├── test_api.py           — endpoint testleri
│   │   └── test_db.py            — veritabanı testleri
│   └── conftest.py               — pytest fixtures
│
├── scripts/
│   ├── fetch_serpapi.py          — SerpAPI'den çek → data/raw/
│   ├── generate_synthetic.py     — temizlik + kural tabanlı alanlar
│   │                                (type, services, fiyat, süre, online,
│   │                                cinsiyet, available/booked_slots) → data/processed/
│   ├── enrich_with_llm.py        — sadece rich_description'ı LLM ile
│   │                                üretip data/processed/'u günceller
│   ├── load_embeddings.py        — Qdrant'a veri yükleme
│   ├── seed_db.py                — PostgreSQL seed
│   │
│   └── constants/                — sentetik veri üretimi için sabit sözlükler
│       ├── __init__.py
│       ├── business_types.py     — QUERY_TERM_TO_TYPE
│       ├── service_taxonomy.py   — SERVICE_TAXONOMY (ağırlıklı)
│       ├── pricing.py            — PRICE_RANGES_TL, APPOINTMENT_DURATIONS_MIN
│       ├── attributes.py         — ONLINE_AVAILABLE, GENDER_PREFERENCE_WEIGHTS
│       └── working_hours.py      — WORKING_HOURS_TEMPLATE, jitter, hafta sonu olasılıkları
│
├── docker/
│   ├── Dockerfile.backend        — backend image
│   └── Dockerfile.frontend       — frontend image
│
└── frontend/                     — React (21s dev MCP)
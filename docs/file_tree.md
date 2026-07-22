seekbind/
├── .env                          — API key'ler
├── .env.example                  — örnek env şablonu
├── .gitignore                    — .env dahil
├── requirements.txt              — bağımlılıklar
├── docker-compose.yml            — PG + Qdrant + Langfuse
├── docker-compose.prod.yml       — production overrides
├── README.md
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
    ├── fetch_serpapi.py          — SerpAPI'den çek → data/raw/
    ├── enrich_with_llm.py        — LLM ile zenginleştir → data/processed/
    ├── generate_synthetic.py     — takvim slotları üret → data/processed/
│   ├── load_embeddings.py        — Qdrant'a veri yükleme
│   └── seed_db.py                — PostgreSQL seed
│
├── docker/
│   ├── Dockerfile.backend        — backend image
│   └── Dockerfile.frontend       — frontend image
│
└── frontend/                     — React (21s dev MCP)
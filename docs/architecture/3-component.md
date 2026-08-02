# 3 — Component Diyagramı (Backend API)

[2-container.md](2-container.md)'deki "Backend API" kutusunun içine
yakınlaşıyor — bu container'ın kendi içinde hangi mantıksal parçalara
bölündüğünü gösteriyor. Hâlâ zaman sırası/dallanma yok, sadece statik
"kim kimi çağırıyor" ilişkisi.

```mermaid
C4Component
    title Component Diyagramı — Backend API

    Container_Boundary(api, "Backend API") {
        Component(routes, "API Routes", "FastAPI router", "/recommend, /book, /health uç noktaları")
        Component(middleware, "Middleware", "RateLimitMiddleware, prompt_injection", "İstek girişinde çalışan koruma katmanı")
        Component(rag, "RAG Service", "get_recommendation()", "Intent ayrıştırma + arama + öneri üretimi orkestrasyonu")
        Component(search, "Search Service", "search_providers()", "BM25 + vektör arama + RRF + reranking")
        Component(calendar, "Calendar Service", "book()", "Randevu rezervasyonu, çakışma kontrolü, alternatif önerisi")
        Component(cache, "Cache Layer", "CachedLLMProvider / CachedEmbeddingProvider", "Redis destekli LLM/embedding cache")
        Component(fallback, "Fallback Layer", "FallbackLLMProvider / FallbackEmbeddingProvider", "OpenAI→Ollama otomatik geçiş")
    }

    ContainerDb(postgres, "PostgreSQL")
    ContainerDb(qdrant, "Qdrant")
    ContainerDb(redis, "Redis")
    System_Ext(openai, "OpenAI")
    System_Ext(ollama, "Ollama")
    System_Ext(jina, "Jina")

    Rel(routes, middleware, "istek geçer")
    Rel(middleware, rag, "/recommend")
    Rel(middleware, calendar, "/book")

    Rel(rag, search, "aday işletmeleri ister")
    Rel(rag, fallback, "intent parse + öneri üretimi için LLM çağrısı")
    Rel(rag, postgres, "fiyat eşiği, kullanıcı konumu sorguları")

    Rel(search, fallback, "embedding çağrısı")
    Rel(search, qdrant, "vektör arama")
    Rel(search, jina, "reranking")
    Rel(search, postgres, "işletme detayı, müsaitlik sorguları")

    Rel(calendar, postgres, "slot/randevu sorguları")

    Rel(fallback, cache, "önce cache'e bakar")
    Rel(cache, redis, "cache oku/yaz")
    Rel(fallback, openai, "birincil sağlayıcı")
    Rel(fallback, ollama, "ikincil sağlayıcı")
```

## Notlar

- **Cache Layer, Fallback Layer'ın İÇİNDE sarmalanmış** — kompozisyon
  sırası `Fallback(Cache(OpenAI), Cache(Ollama))`, yani her sağlayıcı
  kendi cache'iyle birlikte fallback zincirine giriyor. Bu diyagramda
  ok yönü (`fallback → cache`) bu sarmalamayı gösteriyor; tam mekanizma
  için bkz. [4-code-provider-fallback-cache.md](4-code-provider-fallback-cache.md).
- **RAG Service ve Search Service ayrı component'ler** ama RAG Service,
  Search Service'i DOĞRUDAN değil `search_providers()` fonksiyonu
  üzerinden çağırıyor — kod düzeyinde ayrı modüller (`backend/services/rag/`
  vs `backend/services/search/`).
- Middleware'in rate limit kısmı Redis'e doğrudan bağlanıyor (cache
  layer üzerinden değil) — basitlik için bu ilişki diyagramda ayrıca
  çizilmedi, `2-container.md`'deki genel `api → redis` ilişkisi bunu
  zaten kapsıyor.

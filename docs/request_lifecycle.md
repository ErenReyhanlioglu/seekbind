# İstek Yaşam Döngüsü — `/recommend`

Bir `/recommend` isteğinin HTTP girişinden yanıta kadar geçtiği tüm
aşamaların, dallanma noktalarının ve dış sistem çağrılarının detaylı
kaydı. Kapsam bilinçli olarak `/recommend`'e (asıl AI akışı) sınırlı —
`/book` (calendar-service) kendi ayrı, daha basit akışına sahip, burada
kapsanmıyor.

## Diyagram 1 — Ana istek akışı

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant RL as RateLimitMiddleware
    participant Route as /recommend (FastAPI)
    participant Svc as get_recommendation()
    participant Redis
    participant LLM as LLM Sağlayıcı
    participant PG as Postgres
    participant Qdrant
    participant BM25 as BM25Index (in-process)
    participant Jina as Jina Rerank API
    participant LF as Langfuse

    Client->>RL: POST /recommend

    RL->>Redis: INCR ratelimit:{ip}:{dakika}
    alt Redis'e ulaşılamıyor
        Note over RL,Redis: fail-open — istek engellenmez
    else dakikalık limit aşıldı
        RL-->>Client: 429 + Retry-After (kısa devre, route'a hiç girmez)
    end

    RL->>Route: call_next()
    Route->>Route: Depends() çözümü — DB session, Qdrant/Redis/LLM/embedding/reranker singleton'ları
    Route->>Svc: get_recommendation(raw_query, user_id, today)
    activate Svc
    Note over Svc,LF: @observe() — tek Langfuse trace'i açılır (tag: "recommend")

    Svc->>Svc: detect_prompt_injection(raw_query) — 15 regex kalıbı (TR/EN), pure in-process
    Note over Svc: True ise sadece flag'lenir, henüz kesilmez

    Svc->>LLM: parse_intent() — temperature=0.0
    Note over LLM,Redis: cache + fallback zinciri — bkz. Diyagram 2
    alt intent parsing başarısız (IntentParsingError)
        Svc->>Svc: ham sorgu + boş SearchFilters() ile devam
    else başarılı
        opt price_preference var, açık min/max fiyat yok
            Svc->>PG: resolve_price_threshold()
        end
    end

    opt near_me = true
        Svc->>PG: get_user_reference_location()
    end

    Svc->>LLM: vector_search() içindeki embed_batch() çağrısı
    Note over LLM,Redis: cache + fallback zinciri — bkz. Diyagram 2
    Svc->>Qdrant: query_points()
    Svc->>BM25: bm25_index.search()
    opt hard filtre var (kategori/fiyat/konum)
        Svc->>Qdrant: fetch_filtered_business_ids() (scroll)
    end
    Svc->>Svc: reciprocal_rank_fusion(vektör, BM25)

    opt tarih/saat müsaitliği filtresi var
        Svc->>PG: fetch_available_business_ids()
    end
    Svc->>PG: _fetch_businesses_by_id()

    Svc->>Jina: rerank(query, documents)
    alt Jina hata/timeout (RerankerServiceError)
        Note over Svc,Jina: RRF sırası korunur — arama hiçbir zaman tamamen çökmez
    end

    opt rating_preference veya distance_reference var
        Svc->>Svc: apply_final_sort() — rating/mesafe RRF ile harmanlanır
    end

    alt arama sonucu boş
        Svc-->>Route: EMPTY_RESULTS_MESSAGE (kısa devre — generation hiç çağrılmaz)
    else prompt injection tespit edildiyse (adım 7'den)
        Svc-->>Route: RECOMMENDATION_FALLBACK_MESSAGE (generation hiç çağrılmaz, arama sonuçları yine döner)
    else
        Svc->>LLM: generate_recommendation() — temperature=0.7 (ASLA cache'lenmez)
        Note over LLM,Redis: sadece fallback, cache atlanır — bkz. Diyagram 2
        alt generation başarısız (RecommendationGenerationError)
            Svc->>Svc: RECOMMENDATION_FALLBACK_MESSAGE'a düş, arama sonuçları yine döner
        end
    end

    Svc->>LF: trace metadata yaz (async, yanıtı bloklamaz)
    deactivate Svc
    Svc-->>Route: RecommendationResponse
    Route-->>Client: 200 OK (GZip'li)
```

### Önemli dallanma noktaları

- **Rate limit (429)** — en dışta, route'a hiç girmeden kesiliyor. Redis'e
  ulaşılamazsa fail-open (istek engellenmez), CLAUDE.md'nin genel
  "zarif bozulma" felsefesiyle tutarlı.
- **Intent parsing başarısız** — sistemi durdurmuyor, ham sorgu + filtresiz
  aramaya düşüyor (daha az isabetli ama yine de bir sonuç döner).
- **Reranker hatası** — arama hiç çökmüyor, RRF sırası (reranker öncesi)
  korunuyor.
- **Boş sonuç / prompt injection / generation hatası** — üçü de aynı
  "sabit mesaja düş" desenini paylaşıyor ama farklı sebeplerden: boş
  sonuçta LLM'e hiç gidilmiyor (gösterilecek bir şey yok), injection'da
  bilerek `generate_recommendation()` atlanıyor (güvenlik), generation
  hatasında LLM çağrısı denendi ama başarısız oldu.

## Diyagram 2 — LLM/Embedding çağrısı: cache + fallback çözümlemesi

Ana akışta 3 yerde ("LLM Sağlayıcı" katmanına her gidişte) aynı desen
tekrar ediyor — ayrı bir diyagram olarak tutuluyor ki ana akış boğulmasın.
Kompozisyon: **`Fallback(Cache(OpenAI), Cache(Ollama))`** — cache,
fallback'in İÇİNDE, yani önce OpenAI-keyed cache'e bakılır, OpenAI
gerçekten başarısız olursa Ollama-keyed cache'e (ayrı bir anahtar
uzayında) geçilir.

```mermaid
sequenceDiagram
    autonumber
    participant Svc as Çağıran (intent/embedding/generation)
    participant FB as FallbackProvider
    participant C1 as CachedProvider (OpenAI)
    participant R1 as Redis
    participant O1 as OpenAI API
    participant C2 as CachedProvider (Ollama)
    participant R2 as Redis
    participant O2 as Ollama (yerel)

    Svc->>FB: complete() / embed_batch()
    FB->>C1: primary.call()
    C1->>R1: cache anahtarını kontrol et
    Note over C1,R1: sadece temperature=0.0 çağrıları cache'lenir (embedding her zaman cache'lenir)
    alt cache hit
        R1-->>C1: kayıtlı yanıt
        C1-->>FB: yanıt (from_cache=true, token sayıları sıfırlanır)
    else cache miss (ya da Redis'e ulaşılamıyor — fail-open)
        C1->>O1: gerçek API çağrısı
        alt OpenAI başarılı
            O1-->>C1: yanıt
            C1->>R1: sonucu cache'e yaz (TTL'li)
            C1-->>FB: yanıt
        else LLMServiceError / EmbeddingServiceError
            O1-->>C1: hata
            C1-->>FB: hata yeniden fırlatılır
            FB->>C2: secondary.call()
            C2->>R2: cache anahtarını kontrol et (Ollama-keyed, AYRI anahtar uzayı)
            alt cache hit
                R2-->>C2: kayıtlı yanıt
            else cache miss
                C2->>O2: gerçek çağrı (yerel)
                O2-->>C2: yanıt
                C2->>R2: sonucu cache'e yaz
            end
            C2-->>FB: yanıt
        end
    end
    FB-->>Svc: nihai yanıt
```

**Not:** Embedding fallback'i (Ollama'ya geçiş) sadece yanıt kaynağını
değil, **hangi Qdrant collection'ının sorgulanacağını da** değiştirir
(`businesses_openai` vs `businesses_ollama-qwen3-embedding-0-6b`) — bu
`contextvars.ContextVar` ile task-scoped takip ediliyor, paylaşılan
`@lru_cache`'li örnekte yarış durumunu önlemek için.

## Dış sistem vs in-process ayrımı

| Aşama | Tür | Koşullu mu? |
|---|---|---|
| Rate limit kontrolü | Redis | Her zaman |
| Intent parsing | LLM API (+ Redis cache) | Her zaman |
| Fiyat eşiği çözümleme | Postgres | Sadece `price_preference` varsa ve açık fiyat yoksa |
| Kullanıcı referans konumu | Postgres | Sadece `near_me=true` ise |
| Embedding + vektör arama | LLM API (+ Redis cache) + Qdrant | Her zaman |
| BM25 arama | in-process (bellek içi) | Her zaman |
| Hard filtre ID çekme | Qdrant | Sadece kategori/fiyat/konum filtresi varsa |
| RRF füzyon | in-process | Her zaman |
| Müsaitlik filtresi | Postgres | Sadece tarih/saat filtresi varsa |
| İşletme detay çekme | Postgres | Her zaman |
| Reranking | Jina API | Her zaman (aday listesi boş değilse) |
| Rating/mesafe son sıralama | in-process | Sadece tercih/referans konum varsa |
| Öneri üretimi | LLM API (cache'siz) | Sadece sonuç boş değilse ve injection yoksa |
| Trace kaydı | Langfuse (async) | Her zaman |

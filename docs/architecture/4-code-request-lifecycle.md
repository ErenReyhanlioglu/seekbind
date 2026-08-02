# 4 — Code: `/recommend` İstek Yaşam Döngüsü

[3-component.md](3-component.md)'deki component'lerin bir `/recommend`
isteğinde tam olarak hangi sırayla, hangi dallanma noktalarıyla
birbirini çağırdığının detaylı kaydı. Bu seviye yoğun — önce önceki 3
seviyeyi okuduysan (sistemin genel şeklini bildiğini varsayarak) takip
etmesi daha kolay olur.

Kapsam `/recommend`'e sınırlı — `/book` (Calendar Service) kendi ayrı,
daha basit akışına sahip, burada kapsanmıyor. LLM/embedding çağrılarının
cache+fallback mekaniği de ayrı bir dosyada — bkz.
[4-code-provider-fallback-cache.md](4-code-provider-fallback-cache.md).

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
    Note over LLM,Redis: cache + fallback zinciri — bkz. diğer dosya
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
    Note over LLM,Redis: cache + fallback zinciri — bkz. diğer dosya
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
        Note over LLM,Redis: sadece fallback, cache atlanır — bkz. diğer dosya
        alt generation başarısız (RecommendationGenerationError)
            Svc->>Svc: RECOMMENDATION_FALLBACK_MESSAGE'a düş, arama sonuçları yine döner
        end
    end

    Svc->>LF: trace metadata yaz (async, yanıtı bloklamaz)
    deactivate Svc
    Svc-->>Route: RecommendationResponse
    Route-->>Client: 200 OK (GZip'li)
```

## Önemli dallanma noktaları

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

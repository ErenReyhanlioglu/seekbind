# 4 — Code: LLM/Embedding Çağrısı — Cache + Fallback Çözümlemesi

[4-code-request-lifecycle.md](4-code-request-lifecycle.md)'de 3 yerde
("LLM Sağlayıcı" katmanına her gidişte — intent parsing, embedding,
öneri üretimi) aynı desen tekrar ediyor. Ana akış diyagramı boğulmasın
diye buraya, tek yere, ayrı çıkarıldı.

**Kompozisyon: `Fallback(Cache(OpenAI), Cache(Ollama))`** — cache,
fallback'in İÇİNDE. Yani önce OpenAI-keyed cache'e bakılır; OpenAI
gerçekten başarısız olursa (sadece o zaman) Ollama-keyed cache'e (ayrı
bir anahtar uzayında) geçilir.

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

## Notlar

- **Redis burada iki kez görünüyor (R1, R2) ama fiziksel olarak aynı
  instance** — sadece farklı anahtar öneki (`llm:openai:...` vs
  `llm:ollama:...`) kullanıyorlar, ayrı Redis sunucuları değil.
- **`temperature=0.0` şartı önemli** — öneri üretimi (`generate_recommendation()`,
  `temperature=0.7`) bu yüzden ASLA cache'lenmiyor, her çağrıda ya
  gerçek OpenAI'ye ya da (OpenAI başarısızsa) gerçek Ollama'ya gidiyor.
  Sadece intent parsing (`temperature=0.0`) ve embedding cache'den
  yararlanabiliyor.
- **Embedding fallback'i, hangi Qdrant collection'ının sorgulanacağını
  da değiştirir** (`businesses_openai` vs `businesses_ollama-qwen3-embedding-0-6b`)
  — bu `contextvars.ContextVar` ile task-scoped takip ediliyor, paylaşılan
  `@lru_cache`'li örnekte yarış durumunu önlemek için.

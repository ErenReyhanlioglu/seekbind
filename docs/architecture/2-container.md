# 2 — Container Diyagramı

[1-context.md](1-context.md)'deki tek "SeekBind" kutusunun içine
yakınlaşıp, kendi işlettiğimiz büyük parçaları (container'ları) ve
aralarındaki ilişkiyi gösteriyor. Henüz bir container'ın İÇİNDE ne
olduğuna bakmıyoruz (bkz. [3-component.md](3-component.md)) — sadece
"hangi parçalar var, kim kiminle konuşuyor".

```mermaid
C4Container
    title Container Diyagramı — SeekBind

    Person(user, "Kullanıcı")

    System_Boundary(seekbind, "SeekBind") {
        Container(frontend, "Frontend", "React (planlanan)", "Henüz geliştirilmedi — Faz 7")
        Container(api, "Backend API", "Python, FastAPI", "Arama, öneri ve randevu uç noktaları")
        ContainerDb(postgres, "PostgreSQL", "İlişkisel DB", "İşletme, randevu slotu, kullanıcı profili verisi")
        ContainerDb(qdrant, "Qdrant", "Vektör DB", "İşletme açıklamalarının embedding'leri")
        ContainerDb(redis, "Redis", "In-memory store", "LLM/embedding cache + rate limit sayaçları")
    }

    System_Ext(openai, "OpenAI API")
    System_Ext(ollama, "Ollama (yerel)")
    System_Ext(jina, "Jina Rerank API")
    System_Ext(langfuse, "Langfuse")
    System_Ext(datebind, "DateBind")

    Rel(user, frontend, "Kullanır (planlanan)")
    Rel(frontend, api, "HTTP/JSON (planlanan)")
    Rel(user, api, "HTTP/JSON (şu an frontend yokken doğrudan)")

    Rel(api, postgres, "SQL — SQLAlchemy async")
    Rel(api, qdrant, "Vektör arama")
    Rel(api, redis, "Cache okuma/yazma + rate limit")
    Rel(api, openai, "LLM + embedding (birincil)")
    Rel(api, ollama, "LLM + embedding (yedek)")
    Rel(api, jina, "Reranking")
    Rel(api, langfuse, "Trace/izleme")
    Rel(api, datebind, "Randevu yönlendirmesi")
```

## Notlar

- **Frontend "planlanan" durumda** — kod yok, sadece hedeflenen teknoloji
  (React) gösteriliyor. Bu satır Faz 7 başlayınca gerçek bir container'a
  dönüşecek.
- **Backend API tek bir container** — mono-repo, tek FastAPI uygulaması;
  ayrı bir mikroservis mimarisi yok. İçindeki modüler bölünme (RAG
  service, search service, calendar service vb.) bir sonraki seviyede
  ([3-component.md](3-component.md)).
- Redis'in iki farklı sorumluluğu (cache + rate limit) burada tek bir
  container olarak gösteriliyor çünkü fiziksel olarak aynı Redis
  instance'ı — mantıksal ayrım component seviyesinde netleşiyor.

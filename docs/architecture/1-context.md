# 1 — Sistem Bağlamı (Context)

SeekBind'i tek bir kutu olarak görüp sadece kimlerle/nelerle konuştuğunu
gösteren en üst seviye. Detay yok — sadece "bu sistem var olmak için
kime bağımlı" sorusuna cevap veriyor.

```mermaid
C4Context
    title Sistem Bağlamı — SeekBind

    Person(user, "Kullanıcı", "Randevu almak isteyen kişi")

    System(seekbind, "SeekBind", "Doğal dilde sorguyu anlayıp uygun hizmet sağlayıcıları önerir")

    System_Ext(datebind, "DateBind", "Randevu rezervasyon platformu")
    System_Ext(openai, "OpenAI", "LLM + embedding API (birincil)")
    System_Ext(ollama, "Ollama (yerel)", "LLM + embedding (yedek — OpenAI başarısız olursa)")
    System_Ext(jina, "Jina AI", "Arama sonuçlarını yeniden sıralayan (reranking) API")
    System_Ext(langfuse, "Langfuse", "LLM çağrılarının izlendiği gözlemlenebilirlik platformu")

    Rel(user, seekbind, "Serbest metin sorgu yazar, öneri + müsait randevu alır")
    Rel(seekbind, datebind, "Kullanıcıyı seçtiği sağlayıcının randevu sayfasına yönlendirir")
    Rel(seekbind, openai, "Intent ayrıştırma, öneri üretimi, embedding")
    Rel(seekbind, ollama, "OpenAI çağrısı başarısız olursa otomatik geçiş")
    Rel(seekbind, jina, "Aday işletmeleri sorguya göre yeniden sıralar")
    Rel(seekbind, langfuse, "Her LLM çağrısını iz olarak gönderir")
```

## Notlar

- **PostgreSQL, Qdrant, Redis bu diyagramda yok** — bunlar SeekBind'in
  kendi sahip olduğu/işlettiği altyapı, dışarıdan bağımsız üçüncü taraf
  sistemler değil. Container seviyesinde (bkz. [2-container.md](2-container.md))
  görünürler.
- **DateBind, SeekBind'in veri kaynağı değil, hizmet ettiği platform** —
  kullanıcı öneriyi SeekBind'de alır ama gerçek randevuyu DateBind
  üzerinden tamamlar.
- Ollama "dış" bir sistem gibi görünse de aslında aynı makinede yerel
  çalışıyor — C4'te "dışarıdan bağımsız bir süreç sınırı" anlamında dış
  sistem sayılır, illa uzak/üçüncü-taraf olması gerekmez.

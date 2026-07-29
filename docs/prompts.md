# Prompt Dosyaları İndeksi

`backend/prompts/` altındaki dosyaların hangi kod tarafından, ne amaçla
kullanıldığının kısa özeti. Detaylı açıklama (yer tutucular, ne zaman
çağrıldığı vb.) burada tekrarlanmaz — ilgili `.py` dosyasındaki
docstring/yorumlarda yaşar, burası sadece bir index. `docs/adr/README.md`
ile aynı mantık.

| Dosya | Kullanan modül | Amaç |
|---|---|---|
| `system.txt` | `backend/services/rag.py` | Genel asistan tanımı + gömülü talimatlara karşı ucuz bir savunma cümlesi |
| `search_intent.txt` | `backend/services/rag.py` | Serbest metin sorguyu yapılandırılmış JSON'a (hard filtreler + semantik kısım) ayrıştırma talimatı — bkz. [ADR-0011](adr/0011-hard-filter-vs-semantic-separation.md) |
| `recommendation.txt` | `backend/services/rag.py` | Arama sonuçlarından doğal dilde öneri metni üretme talimatı |
| `fallback.txt` | `backend/services/rag.py` (planlı) | Arama sonucu boş çıktığında gösterilecek sabit mesaj — henüz doldurulmadı, `rag.py` yazılırken netleşecek |
| `synthetic_enrichment.txt` | `scripts/enrich_with_llm.py` | Veri zenginleştirme (rich_description + keywords) batch prompt'u — zaten çalışıyor |

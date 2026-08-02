# Prompt Dosyaları İndeksi

`backend/prompts/` altındaki dosyaların hangi kod tarafından, ne amaçla
kullanıldığının kısa özeti. Detaylı açıklama (yer tutucular, ne zaman
çağrıldığı vb.) burada tekrarlanmaz — ilgili `.py` dosyasındaki
docstring/yorumlarda yaşar, burası sadece bir index. `docs/adr/README.md`
ile aynı mantık.

| Dosya | Kullanan modül | Amaç |
|---|---|---|
| `system.txt` | `backend/services/rag/intent.py` + `backend/services/rag/recommendation.py` (ortak `backend/services/rag/prompts.py::load_prompt()` üzerinden) | Genel asistan tanımı + gömülü talimatlara karşı ucuz bir savunma cümlesi |
| `search_intent.txt` | `backend/services/rag/intent.py` | Serbest metin sorguyu yapılandırılmış JSON'a (hard filtreler + semantik kısım) ayrıştırma talimatı — bkz. [ADR-0011](adr/0011-hard-filter-vs-semantic-separation.md) |
| `recommendation.txt` | `backend/services/rag/recommendation.py` | Arama sonuçlarından doğal dilde öneri metni üretme talimatı |
| `fallback.txt` | **kullanılmıyor** | Boş dosya, ölü kod — arama sonucu boş çıktığında gösterilen sabit mesaj (`RECOMMENDATION_FALLBACK_MESSAGE`) sonradan `backend/services/rag/service.py`'de hardcoded bir Python sabiti olarak çözüldü, bu dosyaya hiç taşınmadı |
| `synthetic_enrichment.txt` | `scripts/enrich_with_llm.py` | Veri zenginleştirme (rich_description + keywords) batch prompt'u — zaten çalışıyor |

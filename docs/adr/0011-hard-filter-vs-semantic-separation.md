# ADR-0011: Kesin filtre / semantik ayrımı

**Durum:** Kısmen uygulandı
**Tarih:** 2026-07-24

## Bağlam

"Salı sabahı İzmit'te ucuz dişçi" gibi bir sorguda kesin kısıtlar
(gün, saat, konum, fiyat) semantik aramaya karıştırılırsa yanlış
sonuç riski var — bu tarz kısıtlar sabit bir embedding anlamına
sahip değil, ancak bir referans noktasına göre (fiyat aralığı,
mesafe) anlamlı.

## Karar

Kesin filtreler LLM'den yapılandırılmış JSON çıktısı ile (gerçek
Tool Calling API'si değil, `enrich_with_llm.py`'deki gibi
`response_format=json_object`) önce ayrıştırılacak, sadece anlamsal
kısım ("ucuz dişçi" → "dişçi") embedding aramasına gidecek. Kesin
filtreler Qdrant'ın payload filtering'iyle uygulanacak.

## Sonuçlar

Qdrant filtering kısmı (`SearchFilters`: fiyat, konum, gün, cinsiyet,
online) `feature/search-service`'te tamamlandı. Sorgu metninden
otomatik ayrıştırma (LLM intent parsing) henüz yapılmadı —
`feature/reranker` testlerinde bu boşluk somut olarak görüldü:
"ucuz diş kliniği" sorgusunda "ucuz" hem yapılandırılmış filtre
olarak hem serbest metin olarak kaldığında (referans noktası olmadan)
zayıf/yanıltıcı semantik sinyal verdi. Ayrıştırma kısmı
`feature/rag-pipeline`'ın kapsamında.

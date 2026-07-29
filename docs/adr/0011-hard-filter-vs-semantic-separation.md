# ADR-0011: Kesin filtre / semantik ayrımı

**Durum:** Kısmen uygulandı
**Tarih:** 2026-07-24 (karar) · 2026-07-29 (ayrıştırma kısmı büyük ölçüde tamamlandı, konum hariç)

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
otomatik ayrıştırma (LLM intent parsing), `feature/rag-pipeline`'da
(`backend/services/rag/intent.py`) tamamlandı — kategori, fiyat
(fiyat eşiği hesaplamasının detayı için bkz. [ADR-0014](0014-price-threshold-resolution.md)),
cinsiyet, online, hafta sonu, gün/saat müsaitliği ayrıştırılıyor ve
semantik kısım (`semantic_query`) yer adları dahil korunarak embedding
aramasına gidiyor.

**Eksik kalan tek parça: konum (`NearFilter`).** "Yakınımda" gibi
ifadeler için gerçek koordinat çıkarımı yapılmıyor — geocoding/cihaz
konumu altyapısı yok (frontend de henüz yok, Faz 7). Bu, unutulmuş
değil bilinçli bir sınır; roadmap'te de şu an bunu ele alacak bir
branch tanımlı değil. `NearFilter` hâlâ sadece hazır bir
(lat, lon, radius) üçlüsü kabul ediyor, LLM'in bunu doldurması için
bir yol yok.

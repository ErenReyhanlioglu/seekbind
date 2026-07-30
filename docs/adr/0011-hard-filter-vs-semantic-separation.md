# ADR-0011: Kesin filtre / semantik ayrımı

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-24 (karar) · 2026-07-29 (ayrıştırma kısmı büyük ölçüde tamamlandı, konum hariç) · 2026-07-30 (konum, [ADR-0019](0019-distance-as-ranking-signal.md)'da farklı bir yaklaşımla kapatıldı)

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

**Konum, `feat/near-filter`'da ([ADR-0019](0019-distance-as-ranking-signal.md))
kapatıldı — ama bu ADR'nin orijinal metninin varsaydığından FARKLI bir
mekanizmayla.** Gerçek geocoding/cihaz konumu hâlâ yok (frontend de
henüz yok, Faz 7) — bu hâlâ bilinçli bir sınır. Ama `UserProfile`'ın
sabit referans konumu kullanılarak, "yakınımda" (ve "5 km uzaklıkta"
gibi somut mesafe ifadeleri) artık `ParsedIntent.near_me: bool` olarak
ayrıştırılıyor. Kritik fark: konum burada bu ADR'nin diğer kesin
filtreleri (fiyat, cinsiyet, kategori) gibi bir Qdrant `geo_radius`
HARD FİLTRESİ olarak uygulanmadı — sparse kategorilerde (`Cilt Bakım
Merkezi` gibi 2 işletmeli) sıfır sonuç riski yüzünden bilinçli olarak
bir SIRALAMA sinyaline dönüştürüldü (detay ve gerekçe ADR-0019'da).
`NearFilter`/`SearchFilters.near`'ın bu ADR'de tarif edilen
`geo_radius` mekanizması koddan silinmedi ama hâlâ hiçbir yerden set
edilmiyor.

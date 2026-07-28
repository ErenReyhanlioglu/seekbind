# ADR-0013: Reranker sağlayıcısı seçimi

**Durum:** Kabul edildi (bu ADR kendi içinde bir revizyon geçirdi — bkz. Karar geçmişi)
**Tarih:** 2026-07-24 (ilk aday) · 2026-07-27 (gereklilik kanıtlandı) · 2026-07-28 (karar revize edildi)

## Bağlam

RRF ile birleştirilmiş (bkz. [ADR-0010](0010-hybrid-search-with-rrf.md))
aday havuzunun, sorgu ile aday arasındaki ilişkiyi birlikte
değerlendiren bir cross-encoder ile yeniden sıralanması gerekiyordu.

## Kanıt: reranker gerçekten gerekli mi? (2026-07-27)

`scripts/diagnostics/smoke_test_search.py`'nin `before_reranker`
snapshot'ı
(`evaluation/results/diagnostics/search_smoke_test/before_reranker_2026-07-27T19-48-34.json`),
"ucuz diş kliniği" sorgusunda hem BM25 hem vektör aramasının
veteriner kliniklerini yüksek sırada döndürdüğünü gösterdi —
muhtemel sebep, veteriner kliniklerinin hizmet açıklamalarında evcil
hayvan diş bakımından bahsetmesi (gerçek ama yanlış-tür bir
örtüşme: "diş" kelimesi ortak ama "insan diş kliniği" bağlamı
değil). BM25'te bazı veteriner klinikleri gerçek diş kliniklerinden
bile yüksek skorladı (8.99 vs 6.06), vektör top-15'inde 5 veteriner
kliniği çıktı. İki farklı arama yönteminin de aynı karışıklığı
göstermesi, basit bir eşikleme/ağırlık ayarının yetmeyeceğini —
gerçekten sorgu ve adayı birlikte değerlendiren bir cross-encoder
reranking'in gerektiğini ampirik olarak doğruladı.

## Karar geçmişi

**İlk karar (2026-07-24):** Aday olarak `bge-reranker-v2-m3`
belirlendi — hafif, çok dilli (Türkçe dahil) bir cross-encoder,
LLM tabanlı reranking'e göre çok daha düşük gecikme, `<2s` yanıt
hedefi için uygun görünüyordu. Ancak bu seçim karşılaştırma
yapılmadan, sadece "LLM tabanlı reranking'den hızlı" gerekçesiyle
yapılmıştı — gerçek alternatif (hosted rerank API) hiç
değerlendirilmemişti.

**Revize karar (2026-07-28):** Yerel model yerine hosted API —
**Jina AI (`jina-reranker-v3`)**.

### Değerlendirilen alternatifler

- **Yerel model (`bge-reranker-v2-m3`):** Ek olarak torch/
  transformers gibi ağır bağımlılık, CPU inference'ta gecikme riski,
  ve deploy karmaşıklığı getiriyor.
- **Cohere Rerank:** Artık pay-per-call fiyatlandırması yok, aylık
  $3,250'den başlayan özel instance modeline geçmiş — bu projenin
  ölçeğinde kullanılamaz.
- **Jina AI:** `$0.02/1M token` + her API key'de 10M ücretsiz token
  (pratikte bu projenin ölçeğinde neredeyse ücretsiz). Kendi BEIR/
  MKQA/AirBench sonuçlarına göre `bge-reranker-v2-m3`'ü çok dilli
  performansta geride bırakıyor, 15 kat daha yüksek throughput.

## Karar

Hosted API — Jina AI, `jina-reranker-v3`. `RerankerProvider` bir
Protocol ile soyutlandı ([ADR-0006](0006-llm-based-keywords.md)'daki
gibi Protocol pattern'i tekrar kullanıldı) — ileride yerel bir model
eklemek istenirse config değişikliği yeterli olur, kod değişikliği
gerekmez.

## Sonuçlar

- Hosted seçenek hem daha basit (ağır bağımlılık yok, CPU inference
  gecikme riski yok) hem daha kaliteli çıktı sağlıyor.
- Reranker isteği başarısız olursa RRF sırasına geri dönülüyor
  (graceful degradation) — arama hiçbir zaman tamamen çökmüyor.
- `after_reranker` smoke test karşılaştırması
  (`evaluation/results/diagnostics/search_smoke_test/after_reranker_2026-07-27T21-39-09.json`)
  veteriner/diş klinik karışıklığının reranker sonrası azaldığını
  doğruladı.
- Bilinen sınır: "ucuz", "yakın" gibi karşılaştırmalı ifadeler
  filtreyle aynı anda serbest metinde de kalınca (referans noktası
  olmadan) zayıf sinyal verebiliyor — bu, reranker'ın değil
  [ADR-0011](0011-hard-filter-vs-semantic-separation.md)'in
  kapsamına giren, henüz kapatılmamış bir boşluk.

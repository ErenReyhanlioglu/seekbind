# ADR-0012: Sentetik açıklama mode collapse önlemi

**Durum:** Kabul edildi, doğrulandı
**Tarih:** 2026-07-24 (karar + önlem) · 2026-07-27 (doğrulama)

## Bağlam

LLM'ler yüksek olasılıklı kelimelere yönelme eğiliminde. 478 işletme
için ayrı ayrı üretilen `rich_description` alanları birbirine çok
benzeyip embedding uzayında kümelenirse (mode collapse), semantik
aramanın ayırt ediciliği düşer.

## Karar

`enrich_with_llm.py`'de önlem alındı: batch mimarisi + "birbirine
benzemesin" talimatı + `temperature=0.8` + işletme başına farklı
girdi verisi.

## Sonuçlar

`scripts/diagnostics/check_embedding_diversity.py` ile gerçek
embedding'ler üzerinde doğrulandı: kategoriler-arası ortalama
benzerlik **0.42**, kategori-içi ortalama **0.63-0.78** arası (en
yüksek: Sürücü Kursu — dar hizmet setine sahip olduğu için meşru,
gerçek bir örtüşme). Hiçbir kategori 0.95 uyarı eşiğine yaklaşmadı,
her kategori kategoriler-arası ortalamadan belirgin şekilde
(0.21-0.36 fark) ayrışıyor. Risk yok. Sonuçlar
`evaluation/results/diagnostics/embedding_diversity/businesses_openai_2026-07-27T20-13-12.json`'da
saklı (dosya adı zaman damgalı, script her çalıştırıldığında yeni
bir dosya üretir, önceki sonuç kaybolmaz).

# ADR-0006: LLM tabanlı `keywords` üretimi

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

Arama için senonim/semptom bazlı terimler gerekiyordu (örn. "diş
ağrısı" sorgusunun bir "dişçi" işletmesini bulabilmesi gibi). Bu
tarz terimler kural tabanlı üretilemeyecek kadar açık uçlu.

## Karar

`keywords` alanı `enrich_with_llm.py` ile LLM üzerinden üretiliyor —
ama serbestçe değil, işletmenin zaten sahip olduğu `services`
listesinden türetilerek (senonim/semptom bazlı arama terimleri).

## Sonuçlar

`tags`'ten ([ADR-0005](0005-rule-based-tags.md)) farklı olarak
`keywords` yeni bir öznitelik uydurmuyor, var olan veriden
search-friendly terimler çıkarıyor — halüsinasyon riski LLM
kullanımına rağmen sınırlı kalıyor çünkü girdi zaten işletmenin
kendi verisi.

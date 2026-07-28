# ADR-0002: Ham/işlenmiş verinin git dışında tutulması

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

`data/raw/` (SerpAPI ham çıktıları) ve `data/processed/`
(temizlenmiş + sentetik alan eklenmiş veri) önemli miktarda yer
kaplıyor ve her ikisi de scriptlerle (`fetch_serpapi.py`,
`generate_synthetic.py`, `enrich_with_llm.py`) yeniden üretilebilir.

## Karar

Her iki klasör `.gitignore`'a eklendi, sadece `.gitkeep` ile klasör
yapısı repoda korunuyor.

## Sonuçlar

Repo boyutu küçük kalıyor. Veri kaybı riski, üretim scriptlerinin
tekrar çalıştırılabilir (idempotent/resume destekli) olmasıyla
telafi ediliyor.

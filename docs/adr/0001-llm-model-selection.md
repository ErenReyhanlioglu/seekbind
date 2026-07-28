# ADR-0001: LLM model seçimi

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

Veri zenginleştirme (`enrich_with_llm.py` ile `rich_description` ve
`keywords` üretimi) ve ileride runtime (RAG pipeline) için bir LLM
modeli seçilmesi gerekiyordu. Daha güçlü modeller (Luna/GPT-5.6
ailesi) de değerlendirildi.

## Karar

`gpt-4.1-mini` kullanılacak.

## Sonuçlar

Luna/GPT-5.6 ailesi bu iş için overkill bulundu — maliyet/kalite
dengesi `mini` serisinde daha uygun. Runtime LLM seçimi (Qwen3,
Turkish-LLM gibi alternatiflerle karşılaştırma) ayrı bir konu,
bkz. [ADR-0008](0008-llm-comparison-phase-4.md).

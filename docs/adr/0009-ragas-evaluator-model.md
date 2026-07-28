# ADR-0009: RAGAS evaluator modeli

**Durum:** Kabul edildi (henüz uygulanmadı — Faz 6)
**Tarih:** 2026-07-24

## Bağlam

RAGAS ile farklı modellerin (embedding, LLM) çıktısı karşılaştırılacak
(bkz. [ADR-0007](0007-embedding-model-comparison.md),
[ADR-0008](0008-llm-comparison-phase-4.md)). Değerlendiricinin
(evaluator) kendisi karşılaştırmalar arasında sabit kalmalı, aksi
halde hangi farkın test edilen modelden hangisinin evaluator'dan
geldiği ayırt edilemez.

## Karar

Evaluator olarak OpenAI kullanılacak.

## Sonuçlar

—

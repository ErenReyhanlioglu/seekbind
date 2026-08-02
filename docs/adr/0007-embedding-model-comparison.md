# ADR-0007: Embedding modeli karşılaştırması

**Durum:** Yerini aldı ([ADR-0023](0023-ablation-candidate-models.md))
**Tarih:** 2026-07-24 (ilk bağlam) · 2026-07-31 ([ADR-0023](0023-ablation-candidate-models.md) tarafından supersede edildi)

## Bağlam

Şu an OpenAI `text-embedding-3-small` kullanılıyor
(`feature/embedding-pipeline`, bkz. `docs/roadmap.md` Faz 3). Ama
Türkçe'ye özel alternatifler de var: `embeddingmagibu-200m` ve
`qwen3-embedding:0.6B`. Hangisinin Türkçe semantik aramada daha iyi
performans verdiği henüz karşılaştırılmadı.

## Karar

Bu ADR'nin aday listesi [ADR-0023](0023-ablation-candidate-models.md)
tarafından kesinleştirildi (gerçek Ollama altyapısına karşı doğrulanarak)
— nihai aday kümesi ve gerekçesi için oraya bakın. Karşılaştırmanın
sonucu `feature/ragas-evaluation`'da netleşti — bkz. güncelleme notu.

## Sonuçlar

—

## Güncelleme (2026-08-02): RAGAS sonucu

`feature/ragas-evaluation` kapsamında 100 soruluk 2×2 ablasyon (2 LLM ×
`text-embedding-3-small`/`qwen3-embedding:0.6b`) tamamlandı. Embedding
seçiminin etkisi küçük ve tutarsız yönde çıktı — bazı metriklerde
`qwen3-embedding` hafif önde, bazılarında OpenAI; LLM seçimi (bkz.
[ADR-0008](0008-llm-comparison-phase-4.md)) çok daha belirleyici oldu.
Tam tablo için bkz. [docs/ragas_evaluation.md](../ragas_evaluation.md).

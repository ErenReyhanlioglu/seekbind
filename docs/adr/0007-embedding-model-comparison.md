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
sonucu (hangi embedder kazanacak) hâlâ Faz 6/RAGAS'a bağlı.

## Sonuçlar

—

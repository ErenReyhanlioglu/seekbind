# Architecture Decision Records (ADR)

Bu klasör, SeekBind boyunca alınan mimari kararları kaydeder. Her ADR;
kararın **bağlamını** (o an elimizdeki bilgi/kısıt), kararın kendisini
ve **sonuçlarını** (neye mal oldu, ne kazandırdı) sabitler — kod "ne
yaptığımızı" gösterir, ADR "neden böyle yaptığımızı" gösterir.

Format Michael Nygard'ın önerdiği klasik ADR şablonuna dayanıyor.
Kararlar zamanla değişebilir; eski bir ADR silinmez, gerektiğinde
yeni bir ADR onu **supersede** eder (bkz. [ADR-0013](0013-reranker-provider-selection.md)).

Durum değerleri: **Kabul edildi** · **Planlandı** (henüz karar
verilmedi) · **Kısmen uygulandı** · **Yerini aldı** (başka bir ADR
tarafından supersede edildi)

## İndeks

| No | Başlık | Durum | Tarih |
|----|--------|-------|-------|
| [0000](0000-record-architecture-decisions.md) | ADR kullanma kararı | Kabul edildi | 2026-07-28 |
| [0001](0001-llm-model-selection.md) | LLM model seçimi (gpt-4.1-mini) | Kabul edildi | 2026-07-24 |
| [0002](0002-raw-and-processed-data-excluded-from-git.md) | Ham/işlenmiş verinin git dışında tutulması | Kabul edildi | 2026-07-24 |
| [0003](0003-use-reviews-original-field.md) | `reviews_original` alanının kullanımı | Kabul edildi | 2026-07-24 |
| [0004](0004-bayesian-weighted-rating.md) | Bayesian düzeltmeli `weighted_rating` | Kabul edildi | 2026-07-24 |
| [0005](0005-rule-based-tags.md) | Kural tabanlı `tags` üretimi | Kabul edildi | 2026-07-24 |
| [0006](0006-llm-based-keywords.md) | LLM tabanlı `keywords` üretimi | Kabul edildi | 2026-07-24 |
| [0007](0007-embedding-model-comparison.md) | Embedding modeli karşılaştırması | Planlandı | 2026-07-24 |
| [0008](0008-llm-comparison-phase-4.md) | Runtime LLM karşılaştırması (Faz 4) | Planlandı | 2026-07-28 |
| [0009](0009-ragas-evaluator-model.md) | RAGAS evaluator modeli | Kabul edildi | 2026-07-28 |
| [0010](0010-hybrid-search-with-rrf.md) | Hybrid search (BM25 + vektör, RRF) | Kabul edildi | 2026-07-24 |
| [0011](0011-hard-filter-vs-semantic-separation.md) | Kesin filtre / semantik ayrımı | Kısmen uygulandı | 2026-07-29 |
| [0012](0012-synthetic-description-mode-collapse-mitigation.md) | Sentetik açıklama mode collapse önlemi | Kabul edildi | 2026-07-24 |
| [0013](0013-reranker-provider-selection.md) | Reranker sağlayıcısı seçimi (Jina AI) | Kabul edildi | 2026-07-28 |
| [0014](0014-price-threshold-resolution.md) | Fiyat eşiği hesaplama (LLM tahmini yerine gerçek DB verisi) | Kabul edildi | 2026-07-29 |
| [0015](0015-rating-based-ranking-gap.md) | Puan/kalite bazlı sıralama eksikliği | Kabul edildi, uygulandı | 2026-07-29 |

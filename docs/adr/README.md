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
| [0007](0007-embedding-model-comparison.md) | Embedding modeli karşılaştırması | Yerini aldı (bkz. 0023) | 2026-07-24 |
| [0008](0008-llm-comparison-phase-4.md) | Runtime LLM karşılaştırması (Faz 4) | Yerini aldı (bkz. 0023) | 2026-07-28 |
| [0009](0009-ragas-evaluator-model.md) | RAGAS evaluator modeli | Kabul edildi | 2026-07-28 |
| [0010](0010-hybrid-search-with-rrf.md) | Hybrid search (BM25 + vektör, RRF) | Kabul edildi | 2026-07-24 |
| [0011](0011-hard-filter-vs-semantic-separation.md) | Kesin filtre / semantik ayrımı | Kabul edildi, uygulandı | 2026-07-29 |
| [0012](0012-synthetic-description-mode-collapse-mitigation.md) | Sentetik açıklama mode collapse önlemi | Kabul edildi, doğrulandı | 2026-07-24 |
| [0013](0013-reranker-provider-selection.md) | Reranker sağlayıcısı seçimi (Jina AI) | Kabul edildi | 2026-07-28 |
| [0014](0014-price-threshold-resolution.md) | Fiyat eşiği hesaplama (LLM tahmini yerine gerçek DB verisi) | Kabul edildi, uygulandı | 2026-07-29 |
| [0015](0015-rating-based-ranking-gap.md) | Puan/kalite bazlı sıralama eksikliği | Kabul edildi, uygulandı | 2026-07-29 |
| [0016](0016-langfuse-trace-grouping.md) | Langfuse trace gruplama ve yapılandırılmış metadata | Kabul edildi, uygulandı | 2026-07-29 |
| [0017](0017-tool-calling-not-needed.md) | Tool calling gerekli değil — çoklu-hizmet arama SeekBind 2.0'a bırakıldı | Kabul edildi | 2026-07-29 |
| [0018](0018-calendar-service-booking-and-alternatives.md) | Calendar-service — rezervasyon, çakışma kontrolü ve alternatif önerisi | Kabul edildi, uygulandı | 2026-07-30 |
| [0019](0019-distance-as-ranking-signal.md) | Mesafe — filtre değil, RRF ile birleşen bir sıralama sinyali | Kabul edildi, uygulandı | 2026-07-30 |
| [0020](0020-integration-test-isolation-strategy.md) | Entegrasyon testi izolasyon stratejisi — gerçek DB, SAVEPOINT ve sahte LLM sağlayıcıları | Kabul edildi, uygulandı | 2026-07-30 |
| [0021](0021-db-layer-standards-verification.md) | DB katmanının standartlara uygunluğunu kanıtlayan entegrasyon testleri | Kabul edildi, uygulandı | 2026-07-30 |
| [0022](0022-embedding-llm-cache-layer.md) | Redis destekli embedding + LLM completion cache katmanı | Kabul edildi, uygulandı | 2026-07-30 |
| [0023](0023-ablation-candidate-models.md) | Ablasyon aday modelleri — nihai seçim (LLM + embedding) | Kabul edildi | 2026-07-31 |
| [0024](0024-fallback-mechanism.md) | Sağlayıcılar arası otomatik fallback (LLM + embedding) | Kabul edildi, uygulandı | 2026-07-31 |
| [0025](0025-prompt-injection-detection-strategy.md) | Prompt injection tespiti — kalıp bazlı filtre | Kabul edildi | 2026-07-31 |
| [0026](0026-ci-pipeline-scope.md) | CI pipeline kapsamı — lint, unit + kısmi entegrasyon, birleşik coverage gate'i, build | Kabul edildi | 2026-08-01 |
| [0027](0027-ragas-testset-ground-truth-quality.md) | RAGAS ground truth kalite metodolojisi — `ragas_testset` paketi | Kabul edildi, uygulandı | 2026-08-01 |

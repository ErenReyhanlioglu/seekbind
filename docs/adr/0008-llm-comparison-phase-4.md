# ADR-0008: Runtime LLM karşılaştırması (Faz 4)

**Durum:** Yerini aldı ([ADR-0023](0023-ablation-candidate-models.md))
**Tarih:** 2026-07-24 (ilk bağlam) · 2026-07-28 (OpenAI adayı
gpt-4o-mini olarak netleşti) · 2026-07-31 ([ADR-0023](0023-ablation-candidate-models.md) tarafından supersede edildi)

## Bağlam

Runtime LLM adayı olarak önce `gpt-4.1-mini` düşünülüyordu (bkz.
[ADR-0001](0001-llm-model-selection.md) — o karar veri zenginleştirme
bağlamında verilmişti, runtime için otomatik geçerli sayılmamalı).
Runtime (RAG pipeline, intent parsing, öneri üretimi) için `Qwen3 7B`
ve `Turkish-LLM 7B` (Ollama üzerinden, yerel) alternatifleri
kalite/maliyet açısından henüz kıyaslanmadı.

Proje boyu kalan OpenAI bütçesinin (~$4.83) sıkı olması ve RAGAS
evaluator'ın (bkz. [ADR-0009](0009-ragas-evaluator-model.md))
karşılaştırılan adaylardan biri olmaması gerekliliği (aksi halde
kendi kendini değerlendirme / self-evaluation bias riski oluşur)
nedeniyle OpenAI tarafındaki aday `gpt-4.1-mini`'den `gpt-4o-mini`'ye
çekildi.

## Karar

OpenAI tarafındaki runtime adayı: **`gpt-4o-mini`** — geliştirme
boyunca bu kullanıldı. Ollama tarafındaki aday listesi (`Qwen3 7B` /
`Turkish-LLM 7B`) sonradan gerçek donanıma karşı test edilip
[ADR-0023](0023-ablation-candidate-models.md) ile kesinleştirildi
(`Qwen3 4B`, `Turkish-LLM` düşürüldü) — nihai aday kümesi ve gerekçesi
için oraya bakın. Nihai runtime seçimi `feature/ragas-evaluation`'da
netleşti — bkz. güncelleme notu.

## Sonuçlar

`gpt-4.1-mini`, veri zenginleştirme (ADR-0001) kararı olarak
olduğu gibi kalıyor — bu güncelleme sadece runtime adayını
etkiliyor, enrichment'ı geriye dönük değiştirmiyor.

## Güncelleme (2026-08-02): RAGAS sonucu `gpt-4o-mini`'yi doğruladı

`feature/ragas-evaluation`'daki 100 soruluk 2×2 ablasyonda `gpt-4o-mini`,
`qwen3:4b-instruct-2507-q4_K_M`'yi neredeyse her metrikte belirgin farkla
geçti (özellikle Faithfulness ~0.74 vs ~0.64-0.68, Answer Relevancy
~0.60 vs ~0.40). Tek istisna: expected-empty accuracy'de `qwen3:4b`
(0.8889) `gpt-4o-mini`'den (0.7778) daha iyi. Runtime LLM olarak
`gpt-4o-mini` kararı bu sonuçla ampirik olarak destekleniyor — tam
tablo için bkz. [docs/ragas_evaluation.md](../ragas_evaluation.md).

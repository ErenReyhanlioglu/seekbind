# ADR-0009: RAGAS evaluator modeli

**Durum:** Kabul edildi (genel ilke), spesifik model + ablasyon
kapsamı henüz belirsiz — Faz 6 pilot testine bağlı
**Tarih:** 2026-07-24 (genel ilke) · 2026-07-28 (model adayı ve
açık noktalar eklendi)

## Bağlam

RAGAS ile farklı modellerin (embedding, LLM) çıktısı karşılaştırılacak
(bkz. [ADR-0007](0007-embedding-model-comparison.md),
[ADR-0008](0008-llm-comparison-phase-4.md)). Değerlendiricinin
(evaluator) kendisi karşılaştırmalar arasında sabit kalmalı, aksi
halde hangi farkın test edilen modelden hangisinin evaluator'dan
geldiği ayırt edilemez. Ayrıca evaluator, karşılaştırılan
adaylardan biri olamaz — runtime adayı `gpt-4o-mini` olduğu için
(bkz. ADR-0008) evaluator bu model olursa kendi kendini
değerlendirme (self-evaluation bias) riski oluşur.

## Karar

Evaluator olarak OpenAI kullanılacak — aday: **`gpt-4.1-mini`**
(runtime adaylarından biri değil, ADR-0001'de zaten kalite olarak
onaylanmış). Ancak iki nokta henüz **kesinleşmedi**, Faz 6'da işe
başlarken küçük bir pilot test (1 kombinasyon × birkaç soru,
gerçek token/maliyet ölçümü) ile netleştirilecek:

1. Evaluator'ın spesifik modeli (gpt-4.1-mini varsayımı doğrulanacak)
2. Ablasyon kapsamı — embedding (ADR-0007, 3 aday) × LLM (ADR-0008,
   3 aday) tam 3x3 mü (9 koşu) koşulacak, yoksa embedding ve LLM'i
   ayrı ayrı kıyaslayan daha ucuz kademeli bir tasarım mı
   kullanılacak. 100 soruluk test seti (`feature/ragas-testset`)
   sabit kalacak, değişecek olan sadece kaç kombinasyonun tam
   sette koşulacağı.

## Sonuçlar

—

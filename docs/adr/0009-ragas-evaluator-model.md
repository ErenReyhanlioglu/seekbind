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

## Güncelleme (2026-08-01): Boş sonuçlu sorularda Recall/Precision raporlama

`feature/ragas-testset` sırasında 100 soruluk set (`evaluation/test_set.json`)
hazırlanırken, 9 sorunun (`intent_tags`'te `expected_empty` etiketi —
örn. "online muayene yapan bir diş kliniği var mı?") gerçek DB'ye göre
bilinçli/doğru olarak boş sonuç döndürdüğü belirlendi (bkz.
`scripts/build_ragas_ground_truth.py`). Bu sorularda pipeline doğru
çalışıyorsa `contexts` boş döner.

**Sorun:** Context Recall ve Context Precision, referans cevaptaki
iddiaların `contexts`'te karşılığı olup olmadığını kontrol eder — context
boşsa bu kıyaslama tanımsız/anlamsız hale gelir (RAGAS'ın bunu NaN mı
döndüreceği, otomatik mi atlayacağı `feature/ragas-evaluation`'da gerçek
çalıştırmada görülecek). Faithfulness ve Answer Relevancy bu sorunu
taşımıyor — Faithfulness özellikle bu 9 soruda değerli: sistemin context
olmadan uydurma yapmadığını (halüsinasyon yapmadığını) tam da bu sorular
üzerinden gösteriyor.

**Karar:** Raporlamada:
- **Faithfulness, Answer Relevancy** → tam 100 soru üzerinden ortalama.
- **Context Recall, Context Precision** → `expected_empty` etiketli 9
  soru hariç, 91 soru üzerinden ortalama. Raporda bu dışlamanın nedeni
  (context'siz satırlarda metrik tanım gereği anlamsız) açıkça belirtilir
  — sessizce atlanmaz.

4 metrik de yine aynı 100 soruluk sabit set üzerinden koşulur (ADR-0009'un
genel ilkesiyle tutarlı) — bu sadece koşum sonrası analiz/segmentasyon
kararı, koşum kapsamını değiştirmiyor.

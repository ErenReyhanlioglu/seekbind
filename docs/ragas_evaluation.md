# RAGAS Değerlendirmesi

`feature/ragas-evaluation` branch'inde yapılan, RAG pipeline'ının 2×2
ablasyon ızgarasındaki (bkz. [ADR-0023](adr/0023-ablation-candidate-models.md))
kalitesini ölçen değerlendirme. Test seti `evaluation/test_set.json`'daki
100 sorudan oluşuyor (bkz. `feature/ragas-testset`).

## Yöntem

**Ablasyon ızgarası:** 2 LLM × 2 embedding modeli:

- LLM: `gpt-4o-mini` (bkz. [ADR-0008](adr/0008-llm-comparison-phase-4.md)) ve `qwen3:4b-instruct-2507-q4_K_M`
- Embedding: `text-embedding-3-small` (bkz. [ADR-0007](adr/0007-embedding-model-comparison.md)) ve `qwen3-embedding:0.6b`

**Deterministik metrikler** (ID-bazlı, LLM-yargıçtan bağımsız, ekstra API
maliyeti yok — `test_set.json`'daki `expected_business_ids` ile
pipeline'ın gerçekten döndürdüğü işletme ID'lerinin doğrudan
karşılaştırılmasına dayanıyor, RAGAS'ın cümle-bazlı entailment
ölçümünden daha katı ve doğrudan yorumlanabilir bir sinyal sağlıyor):

- **Top-1 accuracy** — ilk sırada gösterilen işletme gerçekten doğru mu (beklenen kümede mi)
- **Pooled Context Precision** — gösterilen tüm işletmeler (100 sorunun havuzunda birleştirilmiş) arasında gerçekten doğru olanların oranı
- **MRR** (Mean Reciprocal Rank) — doğru işletmeyi ortalama kaçıncı sırada bulduğumuz (1/sıra, sorular arası ortalanmış — hiç bulunamazsa 0)
- **Hit Rate@5** — top-5'te en az bir doğru işletme var mı (ikili — "ne kadarını" değil "hiç mi" sorusu)
- **Recall@5** — beklenen işletme kümesinin top-5'te ne kadarını yakaladığımız (payda `min(5, N)` — N, 5'ten büyükse ham N'e bölmek yapısal bir tavan yaratırdı)
- **Precision@5** — top-5'te gösterilenlerin (soru bazlı ortalama, `Pooled Context Precision`'dan farklı olarak her soru eşit ağırlıklı) ne kadarının doğru olduğu
- **Expected-empty accuracy** — boş dönmesi gereken sorularda gerçekten boş context dönüyor mu (kapsam-tanıma/halüsinasyon kontrolü)

**RAGAS metrikleri** (LLM-yargıç tabanlı, evaluator `gpt-4.1-mini` — bkz. [ADR-0009](adr/0009-ragas-evaluator-model.md)):

- **Faithfulness** — üretilen önerinin sadece sağlanan context'e dayanıp dayanmadığı (halüsinasyon sinyali)
- **Answer Relevancy** — üretilen cevabın kullanıcının asıl sorusuyla ne kadar örtüştüğü
- **Context Precision** — gösterilen context'lerin ne kadarının gerçekten ilgili olduğu
- **Context Recall** — referans cevaptaki iddiaların context tarafından ne kadar desteklendiği

`expected_empty` etiketli 9 soru (bilinçli olarak boş sonuç dönmesi gereken
sorular) Context Precision/Recall'dan hariç tutulup ayrı raporlanıyor —
context boşken bu iki metrik tanım gereği anlamsız kalıyor.

## Sonuçlar

### Deterministik metrikler

| Metrik | gpt-4o-mini + OpenAI-embed | gpt-4o-mini + qwen3-embed | qwen3:4b + OpenAI-embed | qwen3:4b + qwen3-embed |
|---|---|---|---|---|
| Top-1 accuracy | 0.8242 | **0.8352** | 0.7582 | 0.7582 |
| Pooled Context Precision | 0.7655 | **0.7765** | 0.7289 | 0.7312 |
| MRR | 0.8707 | **0.8789** | 0.8185 | 0.8161 |
| Hit Rate@5 | **0.9451** | **0.9451** | 0.9011 | 0.9011 |
| Recall@5 | 0.8022 | **0.8132** | 0.7451 | 0.7473 |
| Precision@5 | 0.7670 | **0.7780** | 0.7165 | 0.7187 |
| Expected-empty accuracy | 0.7778 | 0.7778 | **0.8889** | **0.8889** |

### RAGAS metrikleri

| Metrik | gpt-4o-mini + OpenAI-embed | gpt-4o-mini + qwen3-embed | qwen3:4b + OpenAI-embed | qwen3:4b + qwen3-embed |
|---|---|---|---|---|
| Faithfulness | 0.7401 | **0.7432** | 0.6439 | 0.6779 |
| Answer Relevancy | 0.5943 | **0.6081** | 0.3962 | 0.4063 |
| Context Precision | **0.4521** | 0.4227 | 0.4060 | 0.3893 |
| Context Recall (tümü) | 0.5367 | **0.5633** | 0.5017 | 0.4950 |
| Context Recall (empty hariç) | 0.5788 | **0.5971** | 0.5513 | 0.5440 |

### Evaluator token kullanımı

`gpt-4.1-mini` evaluator'ının 100 soruyu değerlendirirken harcadığı ham
token sayısı (pipeline'ın kendi çalışma zamanı maliyeti DEĞİL — bu sadece
RAGAS'ın kendi yargılama maliyeti):

| | gpt-4o-mini + OpenAI-embed | gpt-4o-mini + qwen3-embed | qwen3:4b + OpenAI-embed | qwen3:4b + qwen3-embed |
|---|---|---|---|---|
| Input token | 934,702 | 933,983 | 931,713 | 933,739 |
| Output token | 148,316 | 160,299 | 199,468 | 204,660 |

Input token dört kombinasyonda da neredeyse aynı (aynı 100 soru, benzer
context uzunluğu). Output token ise `qwen3:4b` kombinasyonlarında belirgin
daha yüksek — evaluator, `qwen3:4b`'nin cevaplarını değerlendirirken daha
fazla akıl yürütme/açıklama üretmiş, düşük skorlarla tutarlı bir gözlem.

## Değerlendirme

**LLM seçimi, embedding seçiminden çok daha belirleyici.** Her iki tabloda
da en büyük fark her zaman LLM ekseninde (gpt-4o-mini vs qwen3:4b) ortaya
çıkıyor — özellikle Answer Relevancy'de (~0.59-0.61 vs ~0.40) ve
Faithfulness'ta (~0.74 vs ~0.64-0.68) belirgin bir fark var. Embedding
seçimi (OpenAI vs qwen3-embedding) her iki LLM grubunda da nispeten küçük
ve tutarsız yönde bir etkiye sahip — bazı metriklerde qwen3-embedding hafif
önde, bazılarında OpenAI.

Bu sonuç, [ADR-0008](adr/0008-llm-comparison-phase-4.md)'de `gpt-4o-mini`'nin
runtime LLM olarak seçilmesini ampirik olarak destekliyor.

Tek istisna: **Expected-empty accuracy**'de `qwen3:4b` (0.8889),
`gpt-4o-mini`'den (0.7778) daha iyi — yani sistemin "bu kapsamda bir
sonucum yok" demesi gereken durumlarda `qwen3:4b` daha disiplinli
davranmış.

## Gecikme ve donanım

Koşumlar şu donanımda yapıldı:

- **CPU:** AMD Ryzen 7 6800H (8 çekirdek / 16 iş parçacığı)
- **RAM:** 32 GB
- **GPU:** NVIDIA GeForce RTX 3050 Laptop, **4 GB VRAM**
- **OS:** Windows 11 Pro

`/recommend` isteği başına (intent parsing + arama/rerank + öneri üretimi
dahil) uçtan uca gecikme, Langfuse trace'lerinden (`get_recommendation()`
zaten `@observe()` ile izleniyor — bkz. [ADR-0016](adr/0016-langfuse-trace-grouping.md)):

| | gpt-4o-mini (iki embedder birleşik*) | qwen3:4b + OpenAI-embed | qwen3:4b + qwen3-embed |
|---|---|---|---|
| Ortalama | 4.40s | 16.14s | 19.55s |
| Medyan | 4.42s | 16.93s | 20.51s |
| Min–Max | 1.35s – 15.52s | 4.81s – 34.39s | 5.84s – 31.63s |

*`gpt-4o-mini`'nin iki embedder kombinasyonu (openai-openai, openai-ollama)
aynı anda, paralel terminallerde çalıştırıldığı için Langfuse'ta zaman
bazlı ayrıştırılamıyor.

**Neden `qwen3:4b` ~4x daha yavaş:** Model (Q4_K_M, 3.5GB) bu kartın 4GB
VRAM'ine tam sığmıyor — `ollama ps` ile doğrulandı, %33 CPU / %67 GPU
paylaşımlı çalışıyor. Bu, hosted bir API'ye (`gpt-4o-mini`) kıyasla
beklenen bir sonuç — gerçek bir mimari/kalite farkı değil, bu spesifik
donanımın VRAM kısıtı. `qwen3:4b + qwen3-embed`'in `qwen3:4b + OpenAI-embed`'den
biraz daha yavaş olması (19.55s vs 16.14s) da aynı sebepten — embedding
çağrısı da yerel Ollama'dan geçtiği için aynı sınırlı VRAM'i LLM ile
paylaşıyor. Yeterli VRAM'i olan bir makinede bu fark büyük ölçüde kapanabilir.

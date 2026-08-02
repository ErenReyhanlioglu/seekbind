# ADR-0023: Ablasyon aday modelleri — nihai seçim (LLM + embedding)

**Durum:** Kabul edildi
**Tarih:** 2026-07-31

## Bağlam

ADR-0007 (embedding karşılaştırması) ve ADR-0008 (runtime LLM
karşılaştırması) ikisi de "Planlandı" durumundaydı — aday listesi vardı
ama gerçek altyapıya karşı hiç doğrulanmamıştı. `feature/fallback-mechanism`
branch'i planlanırken (OpenAI→Ollama fallback), Ollama'nın bu makinede
gerçekten kurulu ve çalışır durumda olduğu keşfedildi (`qwen3:8b`,
`qwen3-embedding:0.6b` zaten çekilmişti) — bu, eski aday listesini gerçek
donanım kısıtlarına karşı test etme fırsatı yarattı.

## Değerlendirilen alternatifler

**`Qwen3 7B`/`8B` (LLM aday) — VRAM'e sığmıyor.** Sistem: RTX 3050 Ti
Laptop (4 GB VRAM). `qwen3:8b` (Q4_K_M, 5.2 GB) gerçek bir istekle test
edildi: partial GPU offload + thinking modu nedeniyle 8.4 token/sn, kısa
bir yanıt için ~40 saniye. 100 sorulu bir RAGAS geçişi için bu tek başına
60+ dakika demek — pratik değil.

**`Turkish-LLM 7B` — aynı sorunu taşıyor, düşürüldü.** ADR-0008'de yer
tutucu olarak duran bu aday için 4B sınıfında Türkçe'ye özel bir
alternatif arandı, bulunamadı. 7B sınıfının VRAM sorunu modelden
bağımsız (boyut sınıfının kendi sorunu) olduğu için, bu aday olduğu
gibi tutulursa `qwen3:8b`'de görülen aynı yavaşlığı taşıyacaktı —
kapsam dışı bırakıldı.

**`Qwen3 4B` — VRAM'e sığan alternatif.** LLM tarafında `qwen3:8b`'nin
yerine ikinci aday olarak seçildi; gerçek karşılaştırma testi model
indirmesi tamamlanınca yapılacak (`feature/fallback-mechanism`
kapsamında). **Not:** gerçek altyapıya karşı test edilirken tam etiket
`qwen3:4b-instruct-2507-q4_K_M` olarak kesinleşti (düz `qwen3:4b`'de
bulunan bir hata nedeniyle) — ayrıntı ve gerekçe için bkz.
[ADR-0024](0024-fallback-mechanism.md).

**`embeddingmagibu-200m` — gerçekliği doğrulanıp eklendi.** Relayed bir
öneri olarak geldi, körü körüne uygulanmadı — Ollama registry sayfası
(`ollama.com/alibayram/embeddingmagibu-200m`) doğrudan kontrol edildi:
gerçek, 768 boyut, 200M parametre, 411 MB, Türkçe odaklı (8192 token
bağlam), Ollama üzerinden paketli (yeni bir provider tipi gerektirmiyor
— mevcut OpenAI-uyumlu istemci deseniyle çalışır). Bilinen sınır: sadece
29 indirme — toplulukça az test edilmiş, "Türkçe'ye özel" olması
otomatik üstünlük garantisi değil, RAGAS sonucunda görülecek.

## Karar

**Runtime LLM adayları (2):** `gpt-4o-mini` (OpenAI), `Qwen3 4B`
(Ollama, yerel).

**Runtime embedding adayları (3):** `text-embedding-3-small` (OpenAI),
`qwen3-embedding:0.6b` (Ollama, yerel), `embeddingmagibu-200m` (Ollama,
yerel, Türkçe özel).

Bu ADR, ADR-0007 ve ADR-0008'i **supersede eder** — aday listesi burada
kesinleşti, iki eski ADR "Yerini aldı" olarak işaretlendi.

`gpt-4.1-mini` (veri zenginleştirme, bkz. ADR-0001, ve RAGAS evaluator,
bkz. ADR-0009) bu kararın kapsamı dışında — runtime LLM adayı değil,
farklı bir rol.

## Sonuçlar

- `feature/fallback-mechanism` branch'i, fallback hedefi olarak
  `Qwen3 4B`'yi (LLM) ve `qwen3-embedding:0.6b`'yi (embedding)
  kullanacak — Ollama tarafındaki tek "canlı" seçim bu ikisi.
  `embeddingmagibu-200m` sadece RAGAS ablasyonunda bir aday, canlı
  fallback hedefi değil (`.env`'deki `OLLAMA_EMBEDDING_MODEL`'i
  değiştirmiyor).
- Faz 6/RAGAS ablasyonu artık 2 (LLM) × 3 (embedding) = 6 kombinasyon
  üzerinden planlanacak (önceden düşünülen 3×3 yerine).

## Bilinen sınır

Bu ADR sadece **aday kümesini** kesinleştiriyor — hangi kombinasyonun
gerçekten en iyi sonucu vereceği Faz 6'daki RAGAS ölçümüne bağlıydı,
bkz. son güncelleme notu.

## Güncelleme (2026-07-31): `embeddingmagibu-200m` ablasyon kapsamından çıkarıldı

`feature/fallback-mechanism` branch'i tamamlanınca, ADR-0024'ün kurduğu
temiz provider soyutlaması üzerinden küçük bir mini-ablasyon (6 kombinasyon:
2 LLM × 3 embedding, gerçek OpenAI+Ollama'ya karşı) çalıştırıldı — asıl
amaç fallback mekanizmasını gerçek çeşitli kombinasyonlarla sınamaktı, ama
bu arada embedder kalitesi hakkında da gerçek sinyal topladı.

**Bulgular:**
- `check_embedding_diversity.py` (3 collection karşılaştırması):
  kategoriler arası ortalama benzerlik `text-embedding-3-small`=0.4177,
  `qwen3-embedding:0.6b`=0.3926 (ikisi de sağlıklı ayrışma), ama
  `embeddingmagibu-200m`=**0.8494** — kategori-içi benzerlikle (0.78-0.91)
  neredeyse aynı seviyede, yani kategoriler arasında anlamlı bir ayrım
  yapamıyor.
- Gerçek bir arama sorgusuyla (`"ucuz diş kliniği"`, ham vektör top-5)
  doğrulandı: `text-embedding-3-small` top-5'te 2/5 gerçek diş kliniği,
  `qwen3-embedding:0.6b` top-3'te 3/3, ama `embeddingmagibu-200m`
  top-5'te **0/5** — fizyoterapist, telefon tamircisi, spor stüdyosu gibi
  tamamen alakasız sonuçlar dönüyor. Reranker (Jina) bunu final sonuçlarda
  büyük ölçüde telafi ediyor, ama bu sadece reranker'ın altta yatan zayıf
  aday havuzunu maskelemesi — reranker'a hiç girmeyen gerçekten alakalı
  bir sonuç asla kurtarılamaz.

**Karar:** `embeddingmagibu-200m` RAGAS ablasyon aday kümesinden
çıkarılıyor — elde bulunan somut kanıtlara göre bu üçüncü adayı dahil
etmek kaynak israfı olurdu (gerçek bir kazanma ihtimali yok). Kod/altyapı
(`OllamaEmbedding`'in genel desteği, doldurulmuş
`businesses_ollama-alibayram-embeddingmagibu-200m` collection'ı) olduğu
gibi kalıyor — silinmiyor, sadece RAGAS'ta kullanılmayacak. İleride farklı
bir Türkçe-özel embedder denenmek istenirse aynı altyapı üzerinden
(`OLLAMA_EMBEDDING_MODEL` + `_OLLAMA_EMBEDDING_DIMENSIONS`'a bir satır)
kolayca eklenebilir.

**Güncel Faz 6/RAGAS kapsamı: 2 (LLM) × 2 (embedding) = 4 kombinasyon**
— `gpt-4o-mini`/`qwen3:4b-instruct-2507-q4_K_M` × `text-embedding-3-small`/
`qwen3-embedding:0.6b`.

**Ayrıca not (Faz 6'da tekrar ele alınacak):** Aynı mini-ablasyonda
`gpt-4o-mini`'nin `temperature=0.0`'da bile iki ayrı gerçek çağrı arasında
tam determinist olmadığı gözlemlendi (21 sorgudan 3'ünde küçük farklar —
belirsiz bir çıkarımda `gender` alanı, `semantic_query`'nin temizlenip
temizlenmemesi). OpenAI'nin `seed` parametresi + `system_fingerprint`
kontrolü bunu "büyük ölçüde" azaltabilir (garanti değil). RAGAS'ta aynı
test setini tekrar tekrar çalıştırırken gözlemlenen skor farkının gerçek
bir kod değişikliğinden mi yoksa API örnekleme gürültüsünden mi geldiğini
ayırt etmek için değerli olabilir — ama Ollama'nın OpenAI-uyumlu
endpoint'inin `seed`'i gerçekten destekleyip desteklemediği doğrulanmadı,
ve cache katmanı zaten canlı trafik için daha güçlü bir determinizm
sağlıyor. Faz 6'nın kendi işi başlarken tekrar değerlendirilecek, şimdilik
eklenmedi.

## Güncelleme (2026-08-02): RAGAS sonucu — kazanan kombinasyon netleşti

`feature/ragas-evaluation`'da 2×2 ızgaranın tamamı 100 soru üzerinde
koşuldu. Sonuç: LLM seçimi (`gpt-4o-mini` vs `qwen3:4b-instruct-2507-q4_K_M`)
embedding seçiminden çok daha belirleyici çıktı — `gpt-4o-mini` neredeyse
her metrikte önde (bkz. [ADR-0008](0008-llm-comparison-phase-4.md)'in
güncelleme notu). Embedding tarafında (`text-embedding-3-small` vs
`qwen3-embedding:0.6b`) fark küçük ve tutarsız yönde. Tam tablo için bkz.
[docs/ragas_evaluation.md](../ragas_evaluation.md).

**Not:** Yukarıdaki `seed` parametresi / determinizm sorusu bu ablasyonda
tekrar ele alınmadı — hâlâ açık, ileride gerçekten gerekirse (örn. RAGAS
sonuçları tekrar tekrar farklı çıkıyor gibi bir şüphe oluşursa) bakılabilir.

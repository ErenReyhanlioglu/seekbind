# SeekBind — AI Destekli Randevu Öneri Sistemi

## Proje Hakkında

SeekBind, [DateBind](https://datebind.com) randevu platformu için geliştirilen yapay zeka destekli bir hizmet arama ve öneri sistemidir. Kullanıcılar doğal dil ile ihtiyaçlarını ifade ederek *"Salı sabahı İzmit'te uygun fiyatlı bir dişçi istiyorum"* kendilerine en uygun hizmet sağlayıcıları ve müsait randevu slotlarını görebilir.

## Nasıl Çalışır?

1. Kullanıcı ihtiyacını serbest metin olarak yazar
2. Sistem bu metni analiz ederek hizmet türü, zaman tercihi, konum ve fiyat gibi parametreleri çıkarır
3. Vektör tabanlı semantik arama ile en uygun hizmet sağlayıcılar belirlenir
4. Kullanıcının mevcut takvimi ve tercihlerine göre filtreleme yapılır
5. Uygunluk skoruna göre sıralanmış sonuçlar kart listesi olarak sunulur
6. Her kartta ilgili sağlayıcının DateBind randevu sayfasına yönlendiren buton bulunur

## Teknik Altyapı

**Veri Kaynağı**
- SerpAPI üzerinden Google Maps verisi (İzmit/Kocaeli bölgesindeki gerçek işletmeler)
- Takvim slotları, hizmet listesi ve fiyat bilgileri sentetik olarak üretilmiştir

**AI Katmanı**
- Embedding: OpenAI `text-embedding-3-small`, `embeddingmagibu-200m` (Türkçe özel), `qwen3-embedding:0.6B`
- LLM: `gpt-4.1-mini`, `Qwen3 7B`, `Turkish-LLM 7B`
- Arama: Semantic Search + Hybrid Search (BM25 + vektör) + Reranking
- RAG (Retrieval Augmented Generation) + Tool Calling mimarisi

**Değerlendirme**
- RAGAS framework ile Faithfulness, Answer Relevancy, Context Precision ve Context Recall metrikleri ölçülmektedir
- Farklı embedding ve LLM kombinasyonları karşılaştırmalı olarak analiz edilmektedir

**Gözlemlenebilirlik**
- Langfuse ile tüm LLM çağrıları, token maliyetleri ve yanıt süreleri izlenmektedir

**Tech Stack**
- Backend: Python, FastAPI
- Veritabanı: PostgreSQL, Qdrant (vektör DB)
- Frontend: React
- Altyapı: Docker

## Kurulum

**Gereksinimler:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker + Docker Compose

```bash
# 1. Repoyu klonla
git clone https://github.com/ErenReyhanlioglu/seekbind.git
cd seekbind

# 2. Bağımlılıkları kur
uv sync

# 3. Ortam değişkenlerini ayarla
cp .env.example .env
# .env içindeki OPENAI_API_KEY, SERPAPI_API_KEY gibi alanları kendi
# key'lerinle doldur

# 4. Altyapıyı ayağa kaldır (PostgreSQL + Qdrant + Langfuse)
docker compose up -d
```

**Veri pipeline'ı (opsiyonel):** `data/` klasörü repoya dahil değildir
(`.gitignore`), veriyi kendin üretmen gerekir — her adım kendi API
maliyetine sahiptir (SerpAPI ücretsiz plan, OpenAI birkaç kuruş):

```bash
uv run python -m scripts.fetch_serpapi       # SerpAPI'den ham veri çek
uv run python -m scripts.generate_synthetic  # kural tabanlı zenginleştirme
uv run python -m scripts.enrich_with_llm     # LLM ile açıklama/keyword üretimi
```

> **Not:** Proje aktif geliştirme aşamasında — backend API henüz uçtan uca
> çalışır durumda değil, yukarıdaki adımlar veri hazırlama pipeline'ını
> kapsar.

## Lisans

[MIT](LICENSE)

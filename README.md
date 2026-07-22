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
- LLM: `GPT-4o-mini`, `Qwen3 7B`, `Turkish-LLM 7B`
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

## Kapsam

Bu proje TechBind Solutions bünyesinde yürütülen bir staj çalışmasıdır. Mevcut aşamada prototip/demo geliştirme hedeflenmekte olup başarılı sonuçlar alınması durumunda DateBind platformuna entegre edilmesi planlanmaktadır.

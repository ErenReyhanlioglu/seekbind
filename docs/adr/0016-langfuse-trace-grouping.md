# ADR-0016: Langfuse trace gruplama ve yapılandırılmış metadata

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-29

## Bağlam

`feature/llm-service`'te kurulan minimal Langfuse izleme (`core/monitoring.py`
+ `langfuse.openai.AsyncOpenAI` sarmalayıcısı), her OpenAI çağrısını otomatik
izliyor ama her çağrı kendi başına, bağımsız bir trace olarak görünüyordu.
Tek bir `/recommend` isteği 2 LLM çağrısı yapıyor (intent parsing + öneri
üretimi, bkz. `feature/rag-pipeline`) — bunlar Langfuse'ta birbirinden
habersiz 2 ayrı trace olarak kayıtlıydı, "bu ikisi aynı isteğin parçasıydı"
bilgisi kayboluyordu. Hiçbir özel metadata da yoktu (hangi adım, hangi
filtre ayrıştı, fallback oldu mu vb.).

Bu, roadmap'in `feature/llm-service` maddesinde bilinçli olarak
ertelenmişti: "çok adımlı akış (intent parsing → arama → öneri) olmadan
trace gruplama/metadata şeması tasarlamak erken olurdu, rag-pipeline'ın
gerçek adımları netleşince yeniden yazmak riskliydi."

## Değerlendirilen alternatifler

- **Manuel `trace_id` üretip her `complete()` çağrısına elle taşımak**:
  Reddedildi — kurulu Langfuse SDK'sının (v2.60.10, kaynak kodundan
  doğrulandı: `langfuse/decorators/langfuse_decorator.py`) zaten
  `@observe()` dekoratörüyle contextvar tabanlı bir gözlem yığını sunduğu
  görüldü; bu, aynı işi otomatik ve daha az kod değişikliğiyle yapıyor
  (`langfuse.openai`'nin sarmalayıcısı, aktif bir `@observe()` bağlamı
  varsa `trace_id`'yi kendisi okuyor, bkz. `openai.py` içindeki
  `decorator_context_trace_id`).
- **`@observe()`'ün varsayılan `capture_input`/`capture_output`
  davranışını olduğu gibi bırakmak**: Reddedildi — `get_recommendation()`'ın
  argümanları arasında `session`/`qdrant_client`/`bm25_index` gibi servis
  nesneleri var; bunlar JSON'a çevrilmeye çalışılınca (`langfuse/serializer.py`'deki
  `EventSerializer` kaynak kodundan doğrulandı) çökmüyor ama nesnelerin
  `__dict__`'ini serialize edip dağınık/gereksiz veri üretiyor. Bunun
  yerine `capture_input=False, capture_output=False` + elle
  `langfuse_context.update_current_trace()` ile trace'e ne gireceği
  bilinçli olarak seçildi.
- **Ollama için ayrı bir mekanizma**: Gerekmedi — `langfuse.openai.AsyncOpenAI`
  sarmalayıcısının kaynak kodu (`OpenAiArgsExtractor`, `openai.py`)
  doğrulandı: `name`/`metadata`/`tags` gibi Langfuse'a özel kwarg'lar,
  gerçek API çağrısına gönderilmeden önce client-side'da tamamen
  tüketiliyor (`get_openai_args()` sadece geri kalan kwargs'ı döner).
  Provider-agnostic — Ollama'nın OpenAI-uyumlu endpoint'ine bu parametreler
  hiç ulaşmıyor. **Not**: Ollama bu makinede kurulu değildi, bu sonuç kod
  incelemesiyle doğrulandı; `OllamaLLM`'in kendisi (Langfuse'dan bağımsız
  olarak) gerçek bir Ollama sunucusuna karşı henüz hiç uçtan uca test
  edilmedi — bu, bu branch'e özgü değil, projenin önceden var olan bir
  doğrulama boşluğu.

## Karar

1. **Gruplama**: `get_recommendation()` (`backend/services/rag/service.py`),
   `@observe(name="recommend", capture_input=False, capture_output=False)`
   ile işaretlendi. İçindeki 2 LLM çağrısı (`parse_intent`,
   `generate_recommendation`) otomatik olarak bu trace'in altına, ayrı
   "generation"lar olarak nest oluyor — manuel `trace_id` taşımaya gerek yok.
2. **Per-adım isim/metadata**: `LLMProvider.complete()` (Protocol +
   `OpenAILLM` + `OllamaLLM` + `_run_completion`, `backend/services/llm.py`)
   yeni `langfuse_name: str | None` / `langfuse_metadata: dict[str, object] | None`
   parametreleri aldı, `client.chat.completions.create(name=, metadata=)`'a
   iletiliyor. `parse_intent()` → `name="intent_parsing"`,
   `metadata={"raw_query": ...}`. `generate_recommendation()` →
   `name="recommendation_generation"`, `metadata={"result_count": ...,
   "rating_preference": ...}`.
3. **İstek geneli özet**: `get_recommendation()` içinde `_record_trace()`
   yardımcı fonksiyonu, `langfuse_context.update_current_trace()` ile
   trace'in `input`/`output`/`tags`/`metadata`'sını dolduruyor —
   ayrıştırılan tüm filtreler (kategori, fiyat, cinsiyet, online/hafta
   sonu, müsaitlik, rating_preference), intent parsing/öneri üretiminin
   fallback'e düşüp düşmediği, sonuç sayısı. `tags`, Langfuse arayüzünde
   filtrelemeyi kolaylaştırmak için `"intent_fallback"`/
   `"recommendation_fallback"`/`"empty_results"` gibi durumsal etiketler
   de içeriyor. Fallback bilgisi elde etmek için
   `_resolve_search_query_and_filters`/`_generate_recommendation_with_fallback`
   artık bir `bool` de döndürüyor (fallback'e düşüldü mü).

## Sonuçlar

Gerçek bir `/recommend` isteği ("İzmit'te ucuz dişçi") ile Langfuse'ın
kendi `/api/public/traces` API'sinden doğrulandı (kod incelemesi değil,
gerçek çalışan sistem):

- Trace: `name=recommend`, `tags=["recommend"]`, `input`/`output` doğru,
  metadata'da tüm beklenen alanlar (`category`, `min_price`/`max_price`,
  `rating_preference`, `intent_parsing_fallback`, `recommendation_fallback`,
  `result_count`, `total` vb.) mevcut
- **`observations` sayısı: 2** — iki LLM çağrısı gerçekten tek trace
  altında gruplanmış
- Observation 1: `name=intent_parsing`, `type=GENERATION`,
  `model=gpt-4o-mini-2024-07-18`, `metadata={raw_query, response_format}`
- Observation 2: `name=recommendation_generation`, `type=GENERATION`,
  `model=gpt-4o-mini-2024-07-18`, `metadata={result_count,
  rating_preference, response_format}`

10 yeni birim testi eklendi (178 toplam), `pytest` ve `pyright` temiz,
coverage %100 korundu.

**Bilinen sınır**: Ollama, bu makinede kurulu olmadığı için
`OllamaLLM`/Langfuse entegrasyonu gerçek bir Ollama sunucusuna karşı
uçtan uca hiç test edilmedi — sadece kod seviyesinde (kaynak inceleme)
doğrulandı. Bu, `feature/langfuse-integration`'a özgü değil, önceden var
olan bir boşluk; Ollama kurulumu ayrıca (arka planda) başlatıldı, ileride
gerçek bir doğrulama yapılabilir.

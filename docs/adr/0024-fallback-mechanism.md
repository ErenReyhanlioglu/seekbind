# ADR-0024: Sağlayıcılar arası otomatik fallback (LLM + embedding)

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-31

## Bağlam

`llm.py` ve `rag/service.py`'nin modül docstring'leri baştan beri şunu
söylüyordu: *"Sağlayıcılar arası otomatik fallback (OpenAI hata verirse
Ollama'ya geçme) bilinçli olarak burada değil — bkz.
`feature/fallback-mechanism`"*. ADR-0023 fallback hedefi olarak kullanılacak
aday modelleri (`qwen3:4b`, `qwen3-embedding:0.6b`) kesinleştirmişti ama
mimariyi (kompozisyon sırası, tetikleme politikası, embedding tarafının
LLM'den farklı riskleri) henüz belirlememişti — bu ADR onu tamamlıyor.

## Değerlendirilen alternatifler ve bulgular

**Kompozisyon sırası: `Fallback(Cache(primary), Cache(secondary))`, tersi değil.**
`cache.py`'nin cache anahtarı `self._inner.name`/`self._inner.model`'den
türüyor. Tek bir dış cache `Fallback`'i sarsaydı, anahtar hep `Fallback`'in
statik olarak primary'yi yansıtan kimliğinden türerdi — secondary gerçekten
cevap verdiğinde bu, bir Ollama cevabının `llm:openai:*` anahtarı altına
yazılması demek olurdu. Cache'i içeride (her somut sağlayıcıyı ayrı ayrı
sararak) tutmak, her girdinin gerçekten hangi sağlayıcıdan geldiğini her
zaman doğru etiketler.

**Tetikleme politikası: herhangi bir `LLMServiceError`/`EmbeddingServiceError`, tek deneme, ek retry yok.**
`_run_completion()`/`_run_embedding()` zaten tüm alt-sebepleri (timeout,
bağlantı, API hatası) tek bir hata tipine indirgiyor — daha ince bir sinyal
yok. Bu uygulamadaki her mesaj programatik üretildiği için ("Ollama'da da
reddedilecek bozuk istek" senaryosu yok), kapsamlı bir yakalama doğru
seçim. Faydalı bir yan etki: primary VE secondary ikisi de başarısız olursa
dışarı sızan hâlâ düz bir `LLMServiceError`/`EmbeddingServiceError` —
`rag/intent.py`/`rag/recommendation.py`'nin bunu zaten yakalayan mevcut
`except` blokları hiç değişmeden doğru çalışmaya devam ediyor.

**LLM ve embedding fallback'i simetrik değil.** Bir LLM cevabının Ollama'dan
gelmesi başka hiçbir şeyi etkilemiyor. Ama bir embedding'in Ollama'dan
gelmesi farklı, kıyaslanamaz bir vektör uzayında, farklı boyutta bir sonuç
demek — `get_qdrant_collection_name()` collection kimliğini `provider.name`'den
türetiyor. İki somut sonuç:
- `FallbackEmbeddingProvider.name`/`.model`/`.dimension`, o anki asyncio
  task'ında en son hangi sağlayıcının gerçekten kullanıldığını
  `contextvars.ContextVar` ile takip ediyor (Langfuse'un kendi
  `@observe()`/`langfuse_context` mekanizmasıyla aynı desen) — çünkü
  `get_embedding_provider()` `@lru_cache`'li tek bir paylaşılan örnek
  döndürüyor, düz bir instance attribute eşzamanlı isteklerde yarış
  durumuna girip yanlış isteğin yanlış Qdrant collection'ına gitmesine yol
  açardı. Bunun gerçekten işe yaradığı `tests/unit/test_fallback.py::test_concurrent_tasks_do_not_leak_identity_across_each_other`
  ile kanıtlandı (iki eşzamanlı task, biri fallback'e zorlanmış biri değil).
- `get_embedding_provider()` yeni bir `allow_fallback: bool = True` parametresi
  aldı. `scripts/load_embeddings.py` `allow_fallback=False` kullanıyor —
  toplu yüklerken OpenAI geçici kesilirse bir kısım vektörün sessizce
  Ollama'nın farklı anlamsal uzayından aynı collection'a yazılması testle
  yakalanamayan kalıcı bir veri bozulması olurdu; bu senaryoda fail-fast
  tercih edildi.

**`.name` çakışma düzeltmesi.** Collection adı artık sabit `"ollama"` değil,
`f"ollama-{model_etiketi_temizlenmiş}"` (`qwen3-embedding:0.6b` →
`ollama-qwen3-embedding-0-6b`). Birden fazla Ollama-tabanlı embedder
eklenince (bkz. aşağıdaki `embeddingmagibu-200m` notu) otomatik olarak ayrı
collection üretiyor, boyut çakışması yapısal olarak imkânsız.

**`EmbeddingProvider` Protocol'üne `close()` eklendi.** Önceden hiç yoktu —
`main.py`'nin shutdown sırası `get_llm_provider().close()` çağırıyordu ama
eşdeğer bir embedding çağrısı yoktu, `OpenAIEmbedding`'in client'ı hiç
kapatılmıyordu. `OllamaEmbedding` ikinci bir gerçek HTTP client tutacağı
için bu önceden var olan boşluk şimdi düzeltildi.

**`qwen3:4b` yerine `qwen3:4b-instruct-2507-q4_K_M`.** ADR-0023'te aday
genel olarak "Qwen3 4B" diye geçiyordu; gerçek Ollama'ya karşı test edilirken
`qwen3:4b`'de doğrulanmış, açık bir hata bulundu
([ollama/ollama#12234](https://github.com/ollama/ollama/issues/12234)):
`think:false` hem `/api/generate` hem `/api/chat`'te yok sayılıyor, thinking
izi (`</think>` dahil) `content`'e karışıyor — bu, intent parsing'in
kullandığı `response_format=json_object`'i kırardı. Çözüm: Ollama'nın resmi
kütüphanesindeki `qwen3:4b-instruct-2507-q4_K_M` — mimari olarak sadece
non-thinking modu destekleyen ayrı bir model etiketi. `scripts/diagnostics/smoke_test_fallback.py`'nin
`llm_fallback_intent_parsing_produces_clean_json` senaryosu bunu gerçek
altyapıya karşı doğruladı: thinking izi sızmadı, JSON geçerli, gerçek
`parse_intent()` başarılı.

**`OllamaEmbedding.dimension` — statik tablo, dinamik keşif değil.**
İlk implementasyon `_DIMENSION`'ı tek bir sabit (1024, qwen3-embedding'e
göre) olarak hardcode etmişti. `OLLAMA_EMBEDDING_MODEL` geçici olarak
`embeddingmagibu-200m`'e (768 boyut) çevrilip `load_embeddings.py --provider ollama`
çalıştırılınca bu gerçek bir hataya yol açtı: Qdrant collection'ı yanlış
boyutla (1024) oluşturuldu, gerçek 768 boyutlu vektörler upsert'te
reddedildi. Düzeltme: `_OLLAMA_EMBEDDING_DIMENSIONS` adlı statik bir
sözlük + tanınmayan bir model için construction anında fail-fast
`ValueError`. Ollama'nın `/api/tags`'i her modelin `embedding_length`'ini
gerçekten döndürüyor, yani dinamik keşif teknik olarak mümkündü — bilerek
tercih edilmedi, iki gerekçeyle: (1) `EmbeddingProvider.dimension` Protocol'de
senkron bir `@property`, dinamik yapmak `__init__`'i async yapmayı ya da
Protocol'ün genel arayüzünü bozan ayrı bir async init adımı eklemeyi
gerektirirdi; (2) bu sınıf tam olarak fallback'in **ikincili** — devreye
girdiği an zaten bir şeyler ters gitmiş demek, o anda kendi boyutunu
öğrenmek için Ollama'ya ekstra bir ağ çağrısına bağımlı olmak, dayanıklılığın
en çok gerektiği anda yeni bir başarısızlık noktası eklemek olurdu.

## Karar

- `backend/services/fallback.py`: `FallbackLLMProvider`, `FallbackEmbeddingProvider`.
- `backend/services/embedding.py`: `OllamaEmbedding`, `_run_embedding()`
  (OpenAI ile paylaşılan hata-eşleme), `_OLLAMA_EMBEDDING_DIMENSIONS`.
- Canlı fallback hedefi: **LLM** `qwen3:4b-instruct-2507-q4_K_M`, **embedding**
  `qwen3-embedding:0.6b`. `embeddingmagibu-200m` canlı hedef DEĞİL, sadece
  Faz 6 RAGAS ablasyonu için.
- `ACTIVE_LLM_PROVIDER=ollama` iken secondary hiç kurulmuyor (roadmap'in
  yönü hep primary(openai)→secondary(ollama), tersi değil).
- Yeni config: `enable_fallback: bool = True`.

## Sonuçlar

- `tests/unit/test_fallback.py` (16 test, eşzamanlılık izolasyonu dahil),
  `tests/integration/test_fallback.py` (2 test, gerçek Ollama'ya karşı,
  yeni `requires_ollama` marker) — hepsi geçti.
- `scripts/diagnostics/smoke_test_fallback.py`: 8/8 senaryo gerçek
  OpenAI+Ollama'ya karşı geçti.
- `businesses_ollama-qwen3-embedding-0-6b` gerçek 478 işletmeyle dolduruldu
  — embedding fallback sadece kod olarak değil operasyonel olarak da
  çalışır durumda.
- Bonus (bu branch'in zorunlu kapsamı dışında ama düşük maliyetli/yerel):
  `businesses_ollama-alibayram-embeddingmagibu-200m` de dolduruldu, Faz 6
  hazırlığı olarak. `check_embedding_diversity.py` çoklu-collection
  karşılaştırması destekleyecek şekilde genişletildi (bkz. `--collections`) —
  gerçek sonuç `embeddingmagibu-200m`'nin kategoriler arası ayrışmasının
  zayıf olduğunu gösterdi (kategoriler arası benzerlik 0.85, kategori-içiyle
  neredeyse aynı seviyede — `businesses_openai`'nin 0.42'si ve
  `businesses_ollama-qwen3-embedding-0-6b`'nin 0.39'uyla karşılaştırıldığında
  belirgin şekilde zayıf). Bu, RAGAS'ın kesin retrieval metriklerinin yerini
  tutmuyor ama erken bir uyarı sinyali — Faz 6'da dikkate alınmalı.

## Güncelleme (2026-08-02)

Yukarıdaki karar ("canlı sistemde 'aktif embedding sağlayıcısı' diye bir
ayar bilinçli olarak yok") yerel geliştirme ihtiyacıyla revize edildi:
OpenAI bütçesi tükendiğinde localde frontend/arama testi yapabilmek için
`ACTIVE_LLM_PROVIDER`'la simetrik yeni bir config eklendi:
`ACTIVE_EMBEDDING_PROVIDER: Literal["openai", "ollama"] = "openai"`
(`backend/config.py`). `"ollama"` seçilince `get_embedding_provider()`
`OpenAIEmbedding`'i hiç construct etmiyor, doğrudan Redis cache'e sarılmış
`OllamaEmbedding` dönüyor — `FallbackEmbeddingProvider` hiç devreye
girmiyor.

Bu, yukarıdaki asimetri gerekçesini (Ollama'nın farklı vektör uzayı ->
farklı Qdrant collection) geçersiz kılmıyor: `get_qdrant_collection_name()`
hâlâ `provider.name`'den collection adını türetiyor, `"ollama"` seçiliyken
bu doğrudan `businesses_ollama-qwen3-embedding-0-6b`'ye çözülüyor — bu
collection zaten 478 işletmeyle dolu (yukarıdaki "Sonuçlar" bölümü).
Toplu yükleme (`scripts/load_embeddings.py`) davranışı değişmedi, o hâlâ
kendi `--provider` CLI flag'iyle bağımsız çalışıyor.

## Bilinen sınırlar

- Circuit breaker yok — primary çökükken her istek yine de tam
  `LLM_CALL_TIMEOUT_SECONDS`'u bekleyip sonra secondary'ye düşüyor
  (bilinçli: bu ölçekte eklenen karmaşıklık haklı değil).
- Trace metadata'sına "bu istek fallback'e mi düştü" bilgisi eklenmedi
  (`intent_fallback`/`recommendation_fallback` deseniyle tutarlı olurdu ama
  `parse_intent()`/`generate_recommendation()` dönüş tuple'larını
  büyütmeyi gerektirir) — bilinçli olarak bu branch'in kapsamı dışında
  bırakıldı, ileride küçük bir takip işi olabilir.
- `_OLLAMA_EMBEDDING_DIMENSIONS` statik bir tablo — yeni bir Ollama
  embedding modeli eklendiğinde elle güncellenmesi gerekiyor (unutulursa
  sessizce yanlış çalışmak yerine `ValueError` ile hemen patlıyor).

# ADR-0022: Redis destekli embedding + LLM completion cache katmanı

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-30

## Bağlam

Roadmap (Faz 5): "embedding/sonuç cache'leme". Proje kod standartlarının
açık talimatı: aynı metni tekrar embed etme. Kod tabanında `embed_batch()`'in
gerçek sıcak yolu tek bir yer: `search/vector.py`, her `/recommend`
isteğinde kullanıcının sorgusunu embed ediyor, hiç cache'lenmiyordu.

Kapsam tartışmasında (kullanıcıyla) şu kararlara varıldı:

## Değerlendirilen alternatifler

- **Bellek-içi cache (Redis yerine).** Reddedildi — sadece "ölçeklenebilirlik"
  için değil, mekanik bir zorunluluk: gelecekteki RAGAS ablasyon çalışması
  (Faz 6, farklı embedder/LLM kombinasyonlarını test etmek) canlı FastAPI
  process'inden **ayrı bir script** olarak çalışacak. Process-içi bir cache
  o script'e hiç görünmez olurdu.
- **Öneri metnini (`generate_recommendation()`, `temperature=0.7`) de
  cache'lemek.** Reddedildi — `search_providers()` hiçbir zaman
  cache'lenmediği için (canlı DB/Qdrant'a her istekte gidiyor), öneri metni
  cache'inin isabet etmesi tüm arama boru hattının birebir aynı sonucu
  üretmesini gerektiriyor — çok dar bir koşul, kazancı muhtemelen ihmal
  edilebilir, ama beraberinde getirdiği "temperature=0.7'nin kasıtlı
  çeşitliliğini bozma" riski gerçek (bkz. aşağıdaki "bulunan hata").
- **Semantik cache (vektör benzerliğine göre, örn. "ucuz dişçi" ile "uygun
  fiyatlı diş hekimi" sorgularını aynı cache girdisine eşlemek).** Reddedildi
  — bu proje ölçeğinde gerekçesi zayıf, riski somut: yüksek vektör benzerliği
  anlamca eşdeğerlik garantisi vermiyor (örn. "ucuz dişçi" ile "pahalı dişçi"
  yapısal olarak çok benzer ama `price_preference` ters). Yanlış çıkarsa
  kullanıcıya somut yanlış bilgi gösterir — exact-match cache'in "en kötü
  ihtimalle gereksiz cache miss" riskinden farklı bir risk sınıfı. `docs/adr/0017-tool-calling-not-needed.md`'deki
  gibi "SeekBind 2.0" notuyla bilinçli olarak ertelendi.
- **Cache mantığını her sağlayıcı sınıfına ayrı ayrı gömmek.** Reddedildi —
  bunun yerine Protocol'e (herhangi bir `EmbeddingProvider`/`LLMProvider`)
  uyan HERHANGİ bir sağlayıcıyı saran genel bir wrapper/decorator deseni
  (`CachedEmbeddingProvider`/`CachedLLMProvider`) seçildi — RAGAS'ın farklı
  model/embedder kombinasyonlarını denemesi kod tekrarı gerektirmeden
  otomatik cache'lenir.

## Karar

1. **`backend/services/cache.py`** — `CachedEmbeddingProvider`/
   `CachedLLMProvider`, gerçek sağlayıcıyı Redis cache ile sarar.
   Cache anahtarı her zaman sağlayıcı **adı + gerçek model adını** içerir
   (sadece `name`'i değil) — bunun için `EmbeddingProvider`/`LLMProvider`
   Protocol'lerine yeni bir `model: str` property eklendi. Gerekçe: Redis
   kalıcı (process restart'ından etkilenmez), `.env`'de model değişip
   `name` aynı kalsa bile eski cache girdilerinin sessizce yeni modelin
   çıktısıymış gibi kullanılmaması gerekiyor.
2. **Intent parsing'in cache anahtarı, LLM'e giden TAM render edilmiş
   prompt metninden türetiliyor** (ham kullanıcı sorgusundan değil).
   Keşif sırasında bulunan bir detay: `search_intent.txt` prompt'u
   `today_weekday`'i içine gömüyor — aynı sorgu metni farklı günlerde
   LLM'e farklı bir prompt olarak gidiyor ("yarın" gibi göreceli
   ifadeler günün neresi olduğuna bağlı yorumlanıyor). Anahtar tam
   render edilmiş mesaj içeriğinden türetildiği için gün değişince
   otomatik değişiyor, ayrı bir gün-bazlı geçersizleştirme mantığı
   yazmaya gerek kalmadı.
3. **`ENABLE_CACHE` config bayrağı** — kaba bir debug kapatma anahtarı.
4. **Redis'e ulaşılamazsa istek çökmez** — sessizce cache miss gibi
   davranıp gerçek sağlayıcıya düşülür (log ile).
5. **Devridaim (circular import) çözümü:** `cache.py` çalışma zamanında
   `llm.py`'den `ChatMessage`/`LLMResponse`'a ihtiyaç duyuyor, `llm.py`/
   `embedding.py`'nin factory fonksiyonları da `cache.py`'den
   `CachedLLMProvider`/`CachedEmbeddingProvider`'a ihtiyaç duyuyor —
   factory fonksiyonlarının içinde (modül seviyesinde değil) geciktirilmiş
   bir import ile çözüldü (Python'da bu tür "wiring" fonksiyonları için
   standart bir çözüm).

## Bulunan ve düzeltilen gerçek bir hata

Kapsam kararı #2'de ("öneri metnini cache'leme") açıkça reddedilmiş olsa
da, **ilk implementasyon bunu yanlışlıkla ihlal etti**: `get_llm_provider()`
tek bir paylaşılan `CachedLLMProvider` döndürüyor, hem `parse_intent()`
(`temperature=0.0`) hem `generate_recommendation()` (`temperature=0.7`)
aynı örneği kullanıyor — aralarında ayrım yapan bir mekanizma yazılmamıştı.

Sahte sağlayıcılarla yazılan unit/entegrasyon testleri bunu **hiç
yakalayamadı** (her ikisi de kendi izole senaryosunu test ediyordu, iki
farklı `temperature`'ın aynı paylaşılan provider üzerinden etkileşimini
hiç sınamadı). Gerçek OpenAI'a karşı elle yapılan son doğrulamada
(`/recommend`'e aynı sorguyla iki gerçek istek) bulundu: ikinci isteğin
öneri metni **birebir aynı** çıktı — `temperature=0.7`'nin kasıtlı
çeşitliliği sessizce cache tarafından ortadan kaldırılmıştı.

**Düzeltme:** `CachedLLMProvider.complete()`, SADECE `temperature == 0.0`
olan çağrıları cache'liyor (`_DETERMINISTIC_TEMPERATURE` sabiti) — diğer
tüm çağrılar (varsayılan bypass) Redis'e hiç dokunmadan doğrudan gerçek
sağlayıcıya gidiyor. Bu, önceki bir tartışmada değerlendirilip reddedilen
"sadece deterministik olması gereken çağrıları cache'le" fikrinin aslında
doğru mekanik çözüm olduğunu gösterdi — kapsam kararı zaten buydu, sadece
kod bunu net bir kuralla ifade etmiyordu.

Bu hata hem unit hem entegrasyon testlerine regresyon testi olarak eklendi
(`test_complete_bypasses_cache_for_non_deterministic_temperature`), gerçek
OpenAI'a karşı iki kez (hatalı hâli ve düzeltilmiş hâli) elle doğrulandı.

## Sonuçlar

`pytest -m integration`: 16 → 20 (4 yeni test). `pytest`: 241 unit test
(17 yeni). `pyright`: proje genelinde 0 hata.

Ayrıca `scripts/diagnostics/smoke_test_cache.py` eklendi — diğer
`smoke_test_*.py` script'leriyle aynı ailede, ama bilerek GERÇEK OpenAI'a
karşı çalışıyor (sahte sağlayıcılı testler bu branch'teki asıl hatayı hiç
yakalayamamıştı). 13 senaryo, hepsi gerçek altyapıya karşı: isabet/kaçırma,
kısmi batch, model izolasyonu, `enabled=False` bypass, TTL süresinin
gerçekten dolması (`ttl()==-2` sonrası yeniden gerçek çağrı), Redis'e
ulaşılamama fallback'i, gün-bazlı cache anahtarı değişimi, deterministik
olmayan çağrının asla cache'lenmemesi (asıl hatanın regresyon kanıtı) ve
tam `/recommend` uçtan uca akışı — hepsi geçti (13/13). Sonuçlar
`evaluation/results/diagnostics/cache_smoke_test/` altına zengin JSON
olarak kaydediliyor. Script kendi oluşturduğu gerçek cache anahtarlarını
(önce/sonra farkı alarak, toptan silme yapmadan) temizliyor.

**Bilinen sınırlar** (bilerek kapsam dışı):
- Semantik cache (yukarıda "SeekBind 2.0" notuyla ertelendi).
- Reranker (Jina) cache'lenmiyor — aday listesi canlı DB'ye bağlı olduğu
  için isabet oranı düşük olurdu, aynı gerekçeyle öneri metni de dışarıda
  bırakıldı.
- Cache-hit görünürlüğü Langfuse'a `intent_cache_hit` trace metadata'sı
  olarak yansıyor (`rag/service.py`), ama vendor'ın kendi auto-trace'lediği
  LLM çağrı span'inin içine ayrıca işlenmiyor (güvenilir bir API'si
  doğrulanamadı).

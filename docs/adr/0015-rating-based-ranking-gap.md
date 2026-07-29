# ADR-0015: Puan/kalite bazlı sıralama — mimari bir eksiklik

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-29

## Bağlam

[ADR-0004](0004-bayesian-weighted-rating.md), az yorumlu işletmelerin uç
puanlara sahip görünmesini düzelten bir Bayesian `weighted_rating`
hesaplamıştı. `feature/rag-pipeline`'da bu değer nihayet öneri metnine
eklendi (`backend/services/rag/recommendation.py` — `_format_business_for_prompt`,
bkz. [ADR-0014](0014-price-threshold-resolution.md)'ün de aynı branch'te
ele aldığı fiyat eşiği sorunuyla aynı ruh).

Ama bunu manuel olarak test ederken ("İzmit'te en kötü, puanı en düşük
dişçi" — `scripts/diagnostics/smoke_test_rag.py --query`), gerçek DB'deki
en düşük puanlı 5 "Diş Kliniği" ile (4.26-4.62 arası, gerçek sorguyla
karşılaştırıldı) döndürülen sonuçlar **hiç örtüşmedi** — ilk sonuç
aslında 4.9/5 ile veri setindeki en yüksek puanlı işletmelerden biriydi.

Daha ciddi olan: öneri metni "İzmit'te en düşük puana sahip dişçiler
arasında birkaç seçenek bulunuyor" gibi bir cümle kurdu — bu, verilen
gerçek puan verisiyle desteklenmeyen bir iddia, `recommendation.txt`'in
"sadece verilen bilgileri kullan, uydurma" kuralının fiilen ihlali.

### Kök neden

Sistemde puana göre yapılandırılmış bir sıralama/filtre mekanizması yok:

- Intent parsing şemasında (`price_preference` gibi) bir
  `rating_preference` alanı yok.
- Olsa bile, `search_providers()`'ın sıralaması (BM25+vektör RRF
  füzyonu + cross-encoder reranker, bkz. [ADR-0010](0010-hybrid-search-with-rrf.md))
  puanı hiç girdi olarak almıyor.
- "Kötü"/"en düşük puan" gibi kelimeler sadece semantik arama metnine
  (`semantic_query`) karışıyor — bu da anlamsal olarak gerçek puanla
  ilgisiz, çünkü işletme açıklamaları her zaman nötr/olumlu bir tonda
  yazılıyor ([ADR-0006](0006-llm-based-keywords.md)), düşük puanlı bir
  işletmenin açıklaması metinsel olarak yüksek puanlıdan ayırt edilemiyor.

### Neden sadece prompt mühendisliğiyle çözülemez

[ADR-0014](0014-price-threshold-resolution.md)'teki fiyat sorununa
benzer bir durum — LLM'in "bilgisine" güvenmek yerine sistemin gerçek
veriye erişip karar vermesi gerekiyor. Ama fiyattan farklı olarak
(tek bir sayısal eşik yeterliydi, `resolve_price_threshold` ile
çözüldü), puan muhtemelen gerçek bir **sıralama kriteri** istiyor —
arama sonuçlarının kendisinin puana göre yeniden sıralanması/filtrelenmesi
— sadece tek bir eşik değil. Bu, `search_providers()`'ın RRF+reranker
mimarisine yeni bir sinyal eklemek demek ve ADR-0010'un kapsamını
doğrudan etkiliyor — `feature/rag-pipeline`'ın (sadece intent
parsing + öneri üretimi) değil, arama servisinin kendisinin işi.

## Karar

`rating_preference`, `price_preference` gibi bir eşik/filtre DEĞİL, ayrı
bir **sıralama sinyali** olarak modellendi. Gerekçe: "ucuz"/"pahalı"
dilbilimsel olarak bir eşik ifade eder (bir üst/alt sınırın dışını
elemek istersin), ama "en iyi"/"en kötü" bir üstünlük/sıralama ifadesi —
kimseyi elemeden hepsinin o sırada dizilmesini ister. İki alan bu yüzden
kasıtlı olarak asimetrik.

Somut tasarım:

1. **Intent parsing** (`search_intent.txt`, `ParsedIntent.rating_preference`):
   SADECE açık üstünlük ifadesi varsa ("en iyi", "en kötü", "en yüksek/
   düşük puanlı") `"high"`/`"low"` doldurulur — `price_preference` ile
   birebir aynı scoping disiplini, "iyi bir yer" gibi yumuşak ifadeler
   için özel bir mekanizma eklenmedi (reranker zaten yüksek puanlıları
   üstte tutma eğiliminde, ölçülmeden ek karmaşıklık eklenmedi).
2. **Uygulama** (`search/service.py`): RRF/Qdrant'a HİÇ dokunulmadı.
   `search_providers()`, cross-encoder reranker'dan SONRA, sayfalamadan
   ÖNCE `_sort_by_rating()` ile son bir sıralama uyguluyor. `weighted_rating`
   Qdrant payload'ına da eklenmedi — bir eşik/filtre olmadığı için gerek
   yok.
3. **NULL puan davranışı**: `weighted_rating` olmayan işletmeler, sıralama
   yönü fark etmeksizin (hem "high" hem "low") listenin SONUNA ekleniyor.
   Gerçek veride doğrulandı: bu rastgele eksik veri değil, yapısal —
   "Noter" kategorisindeki 8 işletmenin tamamında hem `rating` hem
   `reviews` boş (resmi/regüle bir kurum olduğu için muhtemelen hiç
   Google yorumu almıyorlar). Puanı bilinmeyen bir işletme ne "en iyi"
   ne "en kötü" olarak iddia edilemez.
4. **`recommendation.txt`**: Gerçek smoke test'te ikinci bir sorun ortaya
   çıktı — prompt, sonuç sırasının HER ZAMAN alaka sırası ("ilk işletme
   en iyi eşleşmedir") olduğunu varsayıyordu. `rating_preference` aktifken
   bu yanlış: LLM, düşük puanlı ama "ilk sırada" bir sonucu "en iyi
   eşleşme" sanıp çelişkili biçimde övüyordu. Çözüm: `generate_recommendation()`
   artık `rating_preference`'ı da alıyor, prompt'a sıranın NEDEN puana
   göre olduğunu açıkça anlatan bir bağlam (`ordering_context`) ekliyor.

### Değerlendirilen alternatifler

- **`weighted_rating`'i Qdrant payload'ına ekleyip `price_preference`
  gibi Range filtresiyle pre-filter uygulamak.** Reddedildi: rating bir
  eşik değil sıralama isteği olduğu için filtrelemeye hiç gerek yok;
  ayrıca 478 kaydın payload'ını geri doldurmak (embedding pipeline'ı
  yeniden çalıştırmak) faydasız bir maliyet olurdu.
- **Puanı RRF'ye üçüncü bir sinyal olarak eklemek.** Reddedildi: alaka
  (relevance) ile kalite (rating) sinyallerini aynı füzyon skorunda
  karıştırır — kullanıcı "en kötü" dediğinde alakalı AMA düşük puanlı
  sonuçları istiyor, ikisinin harmanlanmış bir skoru bunu bozar.
- **"Açlık" (starvation) riski göz önüne alınarak havuzu büyütmek.**
  Gerçek veriyle kontrol edildi: `CANDIDATE_POOL_SIZE=40`, ama her
  kategori ≤20 işletme (bkz. Sonuçlar) — tek kategorili sorgularda risk
  pratikte yok, önlem gerekmedi. Kategori belirtilmeyen geniş sorgular
  için risk teorik olarak var ama `availability` filtresinin zaten
  kabul ettiği aynı, önceden var olan bir tradeoff (bkz. Bağlam).

## Sonuçlar

Gerçek DB verisiyle doğrulama (kategori başına işletme sayısı):
tüm 27 kategoriden hiçbiri 20'yi geçmiyor (`CANDIDATE_POOL_SIZE=40`'ın
altında) — bu yüzden reranker sonrası sıralamanın "açlık" riski, tek
kategorili sorgularda pratikte sıfıra yakın.

`weighted_rating` dağılımı (kategori bazlı `percentile_cont` ile
kontrol edildi, bir eşik gerekmediği için kullanılmadı ama karar
sürecine girdi oldu): genel min=3.52, max=4.99, ortalama=4.72,
std=0.20 — kategoriler arası ortalama farkı ~0.45 puana kadar çıkıyor
(Cilt Bakım Merkezi 4.86 - Yüzme Havuzu 4.40), fiyattaki 50x'lik farktan
çok daha küçük ama yine de anlamlı.

Gerçek smoke test, önce/sonra ("İzmit'te en kötü dişçi" sorgusu, 20
Diş Kliniği adayı arasından):

| | Önce (bu ADR'nin bulduğu bug) | Sonra |
|---|---|---|
| İlk sonuç | 4.9/5 (veri setindeki en yüksek puanlılardan biri) | 4.26/5 (gerçek en düşük puanlı) |
| İlk 5 sonuç, gerçek en düşük 5 ile örtüşme | 0/5 | 5/5, birebir aynı sırada |
| Öneri metni | "en düşük puana sahip dişçiler arasında..." (veriyle desteklenmeyen iddia) | "en düşük puanlı diş kliniği... puanı diğer kliniklere göre daha düşük olduğu için dikkatli olunması öneriliyor" (veriyle tutarlı) |

"En iyi dişçi" sorgusu da ayrıca test edildi: ilk 5 sonuç, gerçek en
yüksek puanlı 5 ile birebir aynı sırada örtüştü (4.976'dan başlayarak).

Değişen dosyalar: `search/service.py` (`RatingPreference`, `_sort_by_rating`,
`search_providers()` parametresi), `rag/intent.py` (`ParsedIntent.rating_preference`),
`rag/service.py` (parametrenin hem arama hem öneri üretimine iletilmesi),
`rag/recommendation.py` (`ordering_context`), `search_intent.txt`,
`recommendation.txt`. 14 yeni birim testi eklendi (toplam 118), `pytest`
ve `pyright` temiz.

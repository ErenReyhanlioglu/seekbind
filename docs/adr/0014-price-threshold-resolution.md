# ADR-0014: Fiyat eşiği hesaplama — LLM tahmini yerine gerçek DB verisi

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-29

## Bağlam

[ADR-0011](0011-hard-filter-vs-semantic-separation.md), göreceli fiyat
ifadelerinin ("ucuz", "pahalı") LLM tarafından kategoriye göre "makul bir
sayısal eşiğe" çevrilmesini öngörüyordu — LLM'in Türkiye'deki genel fiyat
seviyelerine dair kendi bilgisine dayanarak.

`feature/rag-pipeline`'da bu uygulandıktan sonra yazılan kapsamlı bir
smoke test script'i (`scripts/diagnostics/smoke_test_rag.py`, gerçek
DB/Qdrant/LLM'e karşı 10 senaryo), bu yaklaşımın güvenilmez olduğunu
gösterdi:

- Üç ayrı "ucuz X" sorgusunda (dişçi, avukat, berber) — kategori her
  seferinde net belirlendi ama LLM `min_price`/`max_price`'ı hiçbirinde
  doldurmadı, sürekli `null` bıraktı.
- Fiyat filtresi uygulanmayınca, "İzmit'te ucuz dişçi" sorgusu 17-20 aday
  döndürdü; ilk 2 sonuç kategorinin **en pahalı** uçlarıydı
  (`price_min` 4662-5369 TL, "Diş Kliniği" kategorisinin gerçek
  price_min 25. percentile'ı olan ~2174 TL'nin çok üzerinde).
- "ucuz avukat" sorgusunda da benzer şekilde `price_min` 9812-14520 TL
  aralığındaki (kategori içinde pahalı sayılan) avukatlar ilk sıralarda
  çıktı.

### Değerlendirilen alternatifler

- **Gerçek OpenAI Tool Calling API'si** (LLM ihtiyaç duyduğunda bir
  "fiyat istatistiği" tool'unu çağırsın): reddedildi. (1) ADR-0011'in
  "gerçek Tool Calling API'si değil, `response_format=json_object`"
  kararını çiğniyor. (2) Intent parsing'e ek bir LLM round-trip'i
  (çağrı → tool sonucu → tekrar cevap) ekleyip maliyeti/gecikmeyi
  artırıyor — bu, `feature/llm-service`'ten beri özenle kaçınılan bir şey.
- **LLM'in fiyat tahminini iyileştirmek** (daha zorlayıcı bir prompt
  kuralı, örnekler eklemek): denenmedi, çünkü sorunun kökü LLM'in
  Türkiye'deki 478 gerçek işletmenin fiyat dağılımını bilmemesi —
  prompt mühendisliğiyle düzeltilebilecek bir bilgi eksikliği değil.

## Karar

LLM artık sayı tahmin etmiyor. `ParsedIntent`'e yeni bir
`price_preference: Literal["cheap", "expensive"] | None` alanı eklendi —
LLM sadece bu sinyali çıkarıyor (somut bir sayı verilmişse, örn. "300
TL'den ucuza", o zaten `min_price`/`max_price`'a doğrudan gidiyor,
`price_preference` boş kalıyor).

Gerçek sayısal eşik, `backend/services/rag/pricing.py`'deki
`resolve_price_threshold()` ile kategorinin **gerçek fiyat
dağılımından** hesaplanıyor (SQLAlchemy'nin `percentile_cont()`
fonksiyonuyla, tek SQL sorgusunda):

- `"cheap"` → o kategorideki `price_min` değerlerinin 25. percentile'ı,
  `SearchFilters.max_price` olarak kullanılıyor (kategorinin en ucuz
  çeyrekliği)
- `"expensive"` → `price_max` değerlerinin 75. percentile'ı,
  `SearchFilters.min_price` olarak kullanılıyor (en pahalı çeyreklik)
- Kategori belirsizse ya da `price_preference` yoksa `(None, None)`
  döner, filtre uygulanmaz

`build_search_filters()` artık async ve bir `AsyncSession` alıyor —
sadece `min_price`/`max_price` ikisi de boşken ve `price_preference`
doluyken DB'ye gidiyor, somut sayı verilmişse hiç sorgu atmıyor.

## Sonuçlar

`scripts/diagnostics/smoke_test_rag.py` ile önce/sonra karşılaştırması:

| Sorgu | Önce | Sonra |
|---|---|---|
| İzmit'te ucuz dişçi | 17-20 sonuç, ilk 2'si 4662-5369 TL | 5 sonuç, 576-1741 TL aralığında başlıyor |
| ucuz avukat | price_min 9812-14520 TL'ye kadar | price_min 2209-4295 TL arası |
| ucuz berber | 3 sonuç (zaten dar bir aralık) | 2 sonuç, değişmedi |

Somut sayı verilen sorgular ("300 TL'den ucuza") etkilenmedi — o yol
zaten güvenilirdi, değiştirilmedi.

**Bilinen bir uygulama hatası, kendi içinde bulunup düzeltildi:** İlk
implementasyonda `resolve_price_threshold()` yanlış kolonu
sorguluyordu — "cheap" için `price_min` yerine `price_max`'ın
percentile'ı hesaplanmıştı (ve "expensive" için tam tersi), bu da
eşiği anlamsız derecede yüksek/düşük çıkarıyordu. Bu, ilk smoke test
koşusunda dolaylı olarak fark edildi (filtre hâlâ pahalı sonuçları
döndürüyordu); DB'ye doğrudan sorgu atılarak (ücretsiz, LLM'siz)
kesin olarak doğrulandı ve düzeltildi. Unit testler de güçlendirildi —
artık mock'un dönen sayıyı değil, sorgulanan gerçek SQLAlchemy
kolonunu (`price_min` vs `price_max`) kontrol ediyor, böylece aynı
hata ileride ücretli bir LLM çağrısı yapılmadan yakalanabilir.

**Bilinen sınır:** Percentile eşikleri (25/75) sabit kodlanmış, kullanıcı
tarafından ayarlanabilir değil. Kategori başına çok az işletme varsa
(örn. 2-3 işletmeli bir kategori) percentile hesaplaması az sayıda
veri noktasına dayanır, istatistiksel olarak zayıf olabilir — bu,
projenin veri ölçeğinde (478 işletme, bazı kategoriler 2-8 işletme)
kabul edilen bir sınırlama, henüz ayrıca ele alınmadı.

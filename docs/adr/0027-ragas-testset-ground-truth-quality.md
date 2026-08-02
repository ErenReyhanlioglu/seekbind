# ADR-0027: RAGAS ground truth kalite metodolojisi — `ragas_testset` paketi

**Durum:** Kabul edildi, uygulandı — `scripts/ragas_testset/` paketi
yazıldı, gerçek DB'ye karşı doğrulandı (bkz. "Uygulama sonuçları" bölümü).
**Tarih:** 2026-08-01 (karar) · 2026-08-01 (uygulama)

## Bağlam

`evaluation/test_set.json` (100 soru) ve onu üreten
`scripts/build_ragas_ground_truth.py`, gerçek `data/processed/
businesses_enriched.jsonl` verisiyle satır satır incelendi. Dört sorun
tespit edildi:

1. **En kritik:** "simple" etiketli ~32 soru, kategori adının ötesinde
   spesifik bir ihtiyaç/belirti içeriyor ("bel fıtığı için fizyoterapist",
   "gitar dersi veren müzik kursu" gibi). Ama script bu sorularda hiçbir
   sert filtre olmadığında sadece kategori + `weighted_rating`'e göre
   top-5 döndürüyor, sorudaki ihtiyacı hiç kullanmıyor.
   Somut kanıt: q009 ("bel fıtığı") için dönen top-5'in 2/5'i
   (id=49, id=54) hizmetlerinde "fıtığı" kelimesini hiç geçirmiyor —
   sadece rating'leri yüksek olduğu için listede. Buna karşılık gerçekten
   "bel/boyun fıtığı rehabilitasyonu" sunan id=50, 56, 58, 61, 65, 66, 67
   sırf rating'leri biraz düşük diye tamamen dışlanıyor.
2. `price_preference:expensive` test setinde hiç kullanılmıyor —
   `resolve_price_threshold` bunu destekliyor ama içerik boşluğu var.
3. 7 soru çifti (14 soru) neredeyse birebir aynı `expected_business_ids`
   ve referans metni üretiyor (q004/q005, q009/q011, q033/q034,
   q045/q046, q051/q052, q060/q061, q069/q070) — kök neden:
   `_schedule_matches`, `day_of_week` etiketi yoksa `time_of_day`'i hiç
   filtrelemiyor (gerçek pipeline'ın `intent.py`'deki kasıtlı
   davranışıyla tutarlı, ama test setinde sessiz bir tekrar üretiyor).
4. Etiket kombinasyonları sığ (en fazla 2 birlikte), karşılaştırma/
   sayısal-eşik/gürültülü soru tipleri hiç yok.

## Karar

### Paket bağımsızlığı

`scripts/ragas_testset/` bağımsız bir paket olacak — `backend/services/
search/bm25.py` gibi canlı pipeline modüllerini **bilerek** kullanmıyor.
Ground truth üretim aracının test edilen sistemle aynı skorlama ailesine
(BM25, embedding) bağımlı olması, ADR-0009'daki evaluator bağımsızlığı
ilkesini zayıflatırdı.

### Çekirdek istatistiksel primitive: kapsam oranı + entropi + simetrik MIN_COUNT

Bir yüklemin (terim, fiyat eşiği, gün/saat, cinsiyet vb.) bir kategori
içinde **gerçekten ayırt edici** olup olmadığına karar vermek için:

- `f = eşleşen işletme / kategori toplamı`
- `H(f) = -f·log2(f) - (1-f)·log2(1-f)` (Shannon entropisi, [0,1] aralığında)
- **MIN_COUNT = 3, simetrik uygulanır**: hem eşleşen taraf hem
  eşleşMEyen taraf ≥3 olmalı. Gerekçe: 1 eşleşme `named_business`
  intent'iyle çakışır, 2 belirsiz, 3+ gerçek bir "seçenek sun" senaryosu.
  Simetrik uygulama, entropiyi de her iki dejenere uçtan (yakl. 0 ve
  yakl. 1) otomatik uzak tutuyor — ayrı bir "entropi eşiği" icat etmeye
  gerek kalmadı.

**Bu bir hipotez testi DEĞİL, tanımlayıcı bir istatistik** — p-değeri
yok, çoklu test düzeltmesi (FDR/Bonferroni) gerekmiyor. Permütasyon
deneyiyle kanıtlandı: aynı sayıyı (10/20) koruyarak HANGİ işletmelerin
etiketi taşıdığını 5 kez rastgele değiştirdim, entropi her seferinde
tam olarak aynı çıktı (H=1.000000) — çünkü sadece sayıma bağlı, düzenle-
meye duyarsız. Buna karşılık aynı deneyi Fisher'ın kesin testiyle (iki
değişken arasındaki co-occurrence için) tekrarladığımda p-değeri her
seferinde değişti (1.0000 → 0.0230) — orada gerçek bir şans/düzenleme
boyutu var, FDR gerekli. Bu ayrım, "sakal" (Berber'de 20/20 işletmede
geçiyor ama kategori-tanımlayıcılığı mükemmel) örneğiyle de doğrulandı:
kategori×tüm-veri-seti hipotez testi bunu yanlışlıkla "en anlamlı terim"
işaretlerdi, kategori-içi entropi doğru şekilde H=0 (bilgisiz) buluyor.

### Terim eşleştirme: Zemberek morfolojik analiz + lemma-kümesi kesişimi

Türkçe eklemeli bir dil olduğu için soru metnindeki bir kelimeyi
(`boyatmak`) kategori sözlüğündeki farklı yüzey formuyla (`boyama`)
eşleştirmek gerekiyor. Üç yöntem gerçek veride test edildi:

| Yöntem | Sonuç |
|---|---|
| Ham substring/token eşleşmesi | Morfolojik varyasyonu hiç yakalamıyor |
| Snowball Türkçe stemmer | 5 bilinen test çiftinden 3'ü doğru — türetimsel biçimleri (`boyatmak`↔`boyama`, `yıpranmış`↔`yıpranma`) kaçırdı |
| Sabit uzunluk prefix (4 karakter) | 5/5 doğru AMA gerçek sözlükte yanlış-pozitif üretti: `hastalığı`≈`hastanesi` (farklı kökler, ortak alt-dize) — hiçbir sabit uzunluk hem bunu önleyip hem `boyatmak`/`boyama`'yı yakalayamadı |
| **Zemberek (lemma kümesi kesişimi)** | **6/6 doğru** — belirsiz kelimeler için birden fazla aday lemma döndürüyor, "kümelerin kesişip kesişmediği" kuralı hem `boyatmak`≈`boyama`'yı doğru birleştirdi hem `hastalığı`≠`hastanesi`'yi doğru ayırdı |

Zemberek seçildi. Bilinen bedeller: ~95MB indirme, JVM gerekmiyor (saf
Python), `antlr4-python3-runtime==4.8` sabit sürüm bağımlılığı,
12+ aydır güncellenmeyen bir proje (bakım riski) — ama doğruluğu somut
kanıtla gösterildiği için kabul edildi. `setuptools<81` pin'i de gerekli
(83+ sürümlerinde `pkg_resources` kaldırılmış).

### Çok-yüklemli kombinasyon araması (Apriori-tarzı)

Kaç yüklem birlikte test edilsin sorusuna sabit bir sayı yerine
**downward-closure budaması**: bir kombinasyon MIN_COUNT'un altına
düşerse üzerine yeni yüklem eklemenin (sayı sadece küçülebileceği için)
anlamı yok, o dal kesiliyor — derinlik veriden çıkıyor, keyfi seçilmiyor.

İki ek kural, tam ölçekli testte (Fizyoterapist, 27 kategorinin
tamamı) bulunan gerçek sorunlardan çıktı:
- **"Boş yüklem" elemesi:** bir kombinasyondaki her yüklem, çıkarıldığında
  sayıyı gerçekten artırmalı — yoksa o yüklem hiçbir şey daraltmıyor
  demektir, kombinasyonda gereksiz/aldatıcı duruyor.
- **Kanonik sıra:** yüklem tipleri sabit bir sırayla genişletiliyor
  (aynı kombinasyon iki farklı sırada iki kez üretilmesin diye). İlk
  denemede bu eksikti, Fizyoterapist'te 110 "kombinasyon" çıktı, gerçekte
  26'ymış — geri kalanı sıralama tekrarıydı.
- **Collinearity tespiti:** bazı kategorilerde `weekend_open` ile
  `day=saturday` birebir aynı kümeyi işaret ediyor (o kategoride hiç
  Pazar açık işletme yoksa). Bu otomatik tespit edilip tekrarlayan
  yüklem devre dışı bırakılıyor.

**27 kategorinin tamamında robustluk taraması** (tek kategoriyle
yetinmeyip tümünü tarama kararı, kullanıcı talebiyle):
- `online_only` yüklemi **27 kategorinin tamamında dejenere** (her
  kategori ya %0 ya %100 online, hiç karışık değil) — bu yüklem
  kombinasyon motorundan bilerek çıkarılabilir, hiçbir zaman katkı
  vermiyor.
- `gender` yüklemi sadece 4/27 kategoride (Kuaför, Berber, Güzellik
  Salonu, Nail Salon) anlamlı — geri kalan 23 kategoride literal 0/n
  (az değil, sıfır). Bu, mevcut `test_set.json`'daki `expected_empty`
  cinsiyet sorularını (q028, q043) doğruluyor.
- Noter/Muhasebeci/Avukat hafta sonu tamamen kapalı (0/n hem Cumartesi
  hem Pazar) — ofis-mesaisi kategorileri, gerçek dünyayla tutarlı.

### #2 (fiyat "expensive" boşluğu)

Aynı çekirdek fonksiyon, `resolve_price_threshold`'un 75. persentil
yöntemine uygulandı: 27 kategoriden 24'ü sağlıklı (~%25 kapsam, tasarım
gereği beklenen), 3'ü (Göz Doktoru, Cilt Bakım Merkezi, Noter) simetrik
MIN_COUNT'un altında — bu 3 kategoriye "pahalı" sorusu eklenmeyecek.

### #3 (7 çift)

2/7'si (q009/q011, q045/q046) #1'in çözümüyle otomatik ayrışacak
(gerçekten farklı ihtiyaçlar, farklı servis terimleriyle artık
ayrışacaklar). Kalan 5/7 **olduğu gibi bırakılacak** — kök neden
(`time_of_day` tek başına filtre uygulamıyor) gerçek pipeline'ın
kasıtlı davranışını doğru yansıtıyor, "düzeltmek" test setini sistemden
saptırırdı.

### Sinonim/OR-grubu keşfi — kalıcı olarak kapsam dışı

("kilo verme" ↔ "beslenme danışmanlığı" gibi farklı kökler ama aynı
ihtiyaca hizmet eden terimler.) İki yöntem denendi, ikisi de gerçek
veride başarısız:
- **Kategori-içi co-occurrence (Fisher + BH-FDR):** n=20 ile 3486 terim
  çifti test edildi, **FDR sonrası 0 çift anlamlı** — en sık terimler
  bile (fitness üyeliği × vücut geliştirme programı, ikisi de 8-10/20)
  tam bağımsız çıktı (odds ratio=1.0, p=1.0).
- **Global havuzlama (n=478 arka plan):** p-değeri düştü (0.0167) ama
  metodolojik olarak sakat — "beslenme danışmanlığı" sadece Spor
  Salonu'nda geçiyor, alakasız 458 kategoriyle (Noter, Avukat vb.)
  karşılaştırmak yapay bir şişirme, gerçek kanıt değil (confound).

Bu bir eksiklik değil, **ölçülmüş bir tavan** 

### Soru metni üretimi

Ground truth zaten deterministik motorla önceden hesaplanıyor. LLM
sadece kısıtları doğal Türkçeye çevirmek (NLG) için kullanılacak, karar
verici olarak değil — bu ADR-0009'un evaluator bağımsızlığı ilkesini
ihlal etmiyor. Şartlar: sıkı/şablon prompt (sadece verilen kısıtları
kullan, sayı/işletme adı sızdırma), insan gözden geçirmesi zorunlu.
**Gerçek intent-parser'la doğrulama adımı kullanılmayacak** — bir
sağlık kontrolü gibi dursa da, üretilen soruları "sistem doğru
anladı mı" diye filtrelemek, sistemin gerçek zayıflıklarını (garip ama
gerçekçi kullanıcı ifadelerini yanlış anlaması) test setinden gizleme
riski taşıyor.

## Sonuçlar

Metodoloji gerçek veride tekrar tekrar test edilerek (her adımda önce
küçük ölçek, sonra tam ölçek) doğrulandı — hiçbir karar "mantıklı
görünüyor" diye kabul edilmedi. Süreçte 2 kez ("full scale" testte)
baştaki tasarım yanlış çıktı ve düzeltildi:
1. İlk (b) tasarımı (kategori×tüm-veri-seti hipotez testi) kavramsal
   olarak yanlış soruyu cevaplıyordu, entropiye geçildi.
2. İlk kombinasyon araması (sıralama tekrarı + collinearity kontrolü
   yoktu) 110 sahte sonuç üretti, 26 gerçek sonuca düzeltildi.

## Uygulama sonuçları

Paket 14 dosya olarak yazıldı (`coverage_stats.py`, `turkish_lemma.py`,
`term_distinctiveness.py`, `price_distinctiveness.py`, `predicates.py`,
`combination_search.py`, `existing_coverage.py`, `business_lookup.py`,
`ground_truth_filters.py`, `ground_truth_resolvers.py`,
`build_ground_truth.py` + 3 CLI script'i + `reports.py`), hiçbiri 210
satırı geçmiyor (300 kuralının altında). Eski
`scripts/build_ragas_ground_truth.py` (378 satır, kuralı zaten aşıyordu)
silindi, mantığı `ground_truth_filters.py`/`ground_truth_resolvers.py`'ye
taşındı. Çekirdek istatistik fonksiyonları için `tests/unit/scripts/
ragas_testset/` altında 13 birim testi eklendi (kullanıcı onayıyla,
`scripts/` konvansiyonundan sapılarak).

Gerçek DB'ye karşı doğrulama, tasarım aşamasındaki tüm referans
değerlerle birebir örtüştü:
- `scan_term_distinctiveness`: 27 kategori, 612 ayırt edici terim.
  Fizyoterapist'te "fıtık" #1 (10/20, H=1.000), Berber'de "sakal" hiç
  listede yok — beklendiği gibi.
- `scan_price_distinctiveness`: 3/27 dejenere (Göz Doktoru, Cilt Bakım
  Merkezi, Noter) — beklendiği gibi.
- `search_combinations --category Fizyoterapist`: 134 geçerli
  kombinasyon (tasarım aşamasındaki ~26'dan fazla — sebep gerçek
  `term_distinctiveness`'ın keşif aşamasında elle seçtiğim 4 terimden
  çok daha fazla gerçek terim bulması, bir hata değil), 0 tekrar,
  gender/online hiç yok.
- `build_ground_truth`: 100 soru işlendi, 9 boş küme (`expected_empty`
  etiketli 9 soruyla birebir eşleşiyor). Mevcut sorularda henüz
  `service_keyword` etiketi olmadığı için `test_set.json`'da 0 satır
  değişti (beklenen — etiketleme ayrı bir içerik kararı, bu ADR'nin
  kapsamında değil). Mekanizma senkron olmayan bir testle doğrulandı:
  `service_keyword:fıtığı` etiketi eklenince Fizyoterapist için
  `[49, 64, 60, 54, 52]` (id=49/54 "fıtığı" hiç geçmiyor) yerine
  `[50, 52, 56, 58, 60, 61, 64, 65, 66, 67]` (tamamı gerçekten fıtık
  tedavisi sunuyor) döndü — bu ADR'yi başlatan somut örneğin (q009)
  tam olarak çözüldüğünü gösteriyor.

**Henüz yapılmayan:** mevcut `test_set.json` sorularına `service_keyword`
etiketi eklemek (içerik kararı), #4'ün ürettiği kombinasyonları soru
metnine çevirmek (ayrı bir Claude session + insan gözden geçirmesi,
bkz. `question_generation_prompt.md` taslağı).

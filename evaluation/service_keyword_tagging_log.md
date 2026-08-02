# `service_keyword` etiketleme kaydı ve içerik değişiklikleri

## q054 değişikliği (2026-08-01)

`test_set.json`'daki 100 sorunun tamamı tarandığında (sadece elle
bulunan 7 çift değil), `q054`/`q056` (Tesisatçı, "musluk akıtması" /
"kombi bakımı") arasında da birebir aynı `expected_business_ids`
bulundu — ikisi de "simple", ikisinin ihtiyacı için de (musluk, kombi)
`term_distinctiveness` raporunda ayırt edici bir terim yok (aday yok),
yani #1'in mekanizmasıyla düzeltilemeyen, kalıcı bir tekrar.

N=100 sabit tutulacağı için (bkz. ADR-0009, "100 soruluk test seti
sabit kalacak") yeni soru eklemek yerine `q054` **değiştirildi**:
Tesisatçı kategorisinin `price_distinctiveness` raporunda sağlıklı
çıktığı (`expensive`: 6/20, MIN_COUNT'u geçiyor) kullanılarak
`price_preference:expensive` sorusu haline getirildi — hem tekrarı
giderdi hem #2'nin (expensive hiç test edilmiyor) boşluğunu N'i
artırmadan kısmen kapattı. `q056` olduğu gibi bırakıldı.

`q001`/`q085`/`q093` (Diş Kliniği) üçlüsü ve kalan 5 zaman-bazlı çift
(`q004/q005`, `q033/q034`, `q051/q052`, `q060/q061`, `q069/q070`)
kasıtlı olarak dokunulmadan bırakıldı — her biri farklı bir intent
mekanizmasını (üstünlük ifadesi, belirsiz semptom, tek başına
time_of_day) test ediyor, aynı sayısal sonuca varmaları sistemin doğru
davranışı, düzeltilecek bir kusur değil.


Bu dosya, `evaluation/test_set.json`'daki mevcut "simple"/
"vague_implicit_category" sorularına hangi `service_keyword` etiketinin
neden eklendiğinin (ya da neden eklenmediğinin) kalıcı kaydı. Yöntem ve
gerekçe için bkz. [ADR-0027](../docs/adr/0027-ragas-testset-ground-truth-quality.md).

Aday üretimi: soru metni Zemberek ile lemma'landı, kategori sözlüğünün
(`scripts/ragas_testset/scan_term_distinctiveness`, rapor:
`evaluation/results/diagnostics/ragas_testset/term_distinctiveness/2026-08-01T17-17-56.json`)
ayırt edici terimleriyle kesişimi alındı — bu ham eşleşmeler kategori
adıyla çakışan (örn. "salon", "merkez", "servis") ve gramer bağlaçlarıyla
çakışan (örn. "için") sahte eşleşmeleri elemek için elle gözden
geçirildi (bkz. ADR-0027 — bu adımın neden tam otomatik olamayacağı,
"kilo verme" örneğiyle ayrıca tartışıldı).

**Tarih:** 2026-08-01

## Eklenen etiketler

| Soru | Kategori | `service_keyword` | Kapsam | Entropi | Not |
|---|---|---|---|---|---|
| q006 | Psikolog | kaygı | 12/20 | 0.971 | |
| q009 | Fizyoterapist | fıtığı | 10/20 | 1.000 | ADR-0027'yi başlatan örnek |
| q011 | Fizyoterapist | spor | 12/20 | 0.971 | q009 ile artık gerçekten ayrışıyor |
| q012 | Kuaför | boyatmak | 16/20 | 0.722 | Zemberek doğrulama örneği (boyatmak↔boyama) |
| q018 | Güzellik Salonu | makyaj | 12/20 | 0.971 | "cilt" (17/20) çok genel, "makyaj" tercih edildi |
| q021 | Nail Salon | jel | 15/18 | 0.650 | "manikür" ile aynı kapsam, "jel" soru metnine daha yakın |
| q039 | Dil Kursu | ingilizce | 16/20 | 0.722 | |
| q045 | Müzik Kursu | gitar | 16/20 | 0.722 | |
| q046 | Müzik Kursu | piyano | 16/20 | 0.722 | |
| q048 | Oto Servis | periyodik | 14/20 | 0.881 | "servis" (kategori adı) elendi |
| q057 | Klima Servisi | gaz | 14/20 | 0.881 | "servis" (kategori adı) elendi |
| q063 | Veteriner | aşı | 13/20 | 0.934 | |
| q066 | Fotoğrafçı | düğün | 16/20 | 0.722 | Zemberek'in "düğmek"/"düğü" varyantları elendi |
| q071 | Muhasebeci | şirket | 9/20 | 0.993 | |
| q074 | Avukat | boşanma | 14/20 | 0.881 | "avukat"/"dava" (kategori-geneli) elendi |
| q095 | Veteriner | aşı | 13/20 | 0.934 | q063 ile aynı — kasıtlı, vague_implicit_category test edildiği için |

## Etiket eklenmeyenler (aday yok ya da sahte eşleşme elendi)

- **q001** (Diş Kliniği): sadece "klinik"/"izmit" eşleşti — kategori adı/şehir adı, gerçek ihtiyaç değil.
- **q015** (Berber, "sakal tıraşı"): "sakal" terimi kategoride ayırt edici değil — 17 işletmenin **17'sinde de** var (bkz. ADR-0027'nin ana örneği). Tag eklenmedi, doğru davranış.
- **q024** (Epilasyon Merkezi, "lazer epilasyon"): "lazer"/"epilasyon" hiç aday olarak çıkmadı — kategori bu terimler için homojen.
- **q027** (Spor Salonu, "kilo vermek"): "kilo verme" literal olarak sadece 1/20 işletmede geçiyor, MIN_COUNT altında (bkz. ADR-0027'nin (d) sinonim keşfi bölümü — bu sorun kalıcı olarak çözülemez kabul edildi).
- **q030** (Yüzme Havuzu, "yüzme dersi"): "havuz" kategori adına çok yakın, "ders" (H=0.629) zayıf/genel — düşük güvenle dışlandı.
- **q033** (Yoga Stüdyosu, "başlangıç seviyesi"): sadece genel "ders" (17/20) eşleşti, "başlangıç" kavramı veride ayrı bir terim olarak yok.
- **q036** (Özel Ders, "matematik"): "matematik" 18/20 işletmede geçiyor (tamamlayıcı taraf 2 < MIN_COUNT=3) — kategoride neredeyse evrensel, doğrulandı (gerçek DB sorgusuyla).
- **q042** (Sürücü Kursu, "ehliyet almak"): "almak" fiili çok genel, ehliyet almak zaten kategorinin tanımı.
- **q051** (Elektrikçi, "priz arızası"): "arıza" (17/20) çok genel, "priz" özelinde aday yok.
- **q052, q061** (aciliyet/aynı gün): veri modelinde temsil edilemeyen kavramlar (bkz. eski script'teki q100 notuyla aynı gerekçe).
- **q054, q056** (Tesisatçı, musluk/kombi): aday yok.
- **q060** (Telefon Tamiri, "ekranı kırıldı"): düşük güvenli/gürültülü eşleşmeler ("yemek" gibi), dışlandı.
- **q069** (Noter, "vekaletname"): Noter küçük bir kategori (n=8), aday MIN_COUNT sınırının dışında kaldı.
- **q093, q094, q096**: belirsiz semptom/şikayet ifadeleri, veride ayrı bir terime karşılık gelmiyor.

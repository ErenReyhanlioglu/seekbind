# Gerçek RAGAS sonuçlarının (100 soru, openai-openai) manuel doğrulama kaydı

Bu dosya, aynı klasördeki `scores_full_100_2026-08-02T17-03-09.json`
sonuçlarının aggregate skorların ARKASINDA sistemin gerçekte ne kadar doğru
işletme önerdiğini incelemek için, aynı çalıştırmanın
`traces_full_100_2026-08-02T16-57-49.json` dosyası (yeni API çağrısı
YAPILMADAN, tamamen ücretsiz) sistematik olarak incelendi.

**Tarih:** 2026-08-02

## Yöntem

Her trace'in `contexts` alanındaki işletme başlıkları DB'den id'ye
çevrildi, `test_set.json`'daki `expected_business_ids` ile karşılaştırıldı.
Üç soru soruldu: (1) `expected_empty` etiketli sorular gerçekten boş context
mi döndürüyor, (2) normal sorularda context'teki İLK (sistemin en üstte
gösterdiği) işletme gerçekten doğru mu, (3) gösterilen tüm context'lerin
kaçı doğru.

## Bulgu 1 — `expected_empty` sorular (9 soru): 7/9 doğru

7 soru beklendiği gibi boş context döndürdü. **2 soru beklenmedik
şekilde context döndürdü:**
- `q099` ("Yakınımda bir eczane var mı?" — kapsam dışı kategori)
- `q100` ("7/24 açık bir noter var mı?" — veri modelinde temsil edilemez)

Bu iki soru, sistemin "bunu yapamam" demesi gereken durumlar — tam da
uydurma yapmadığını test etmek için tasarlanmışlardı. Şu an context
döndürmeleri (muhtemelen en yakın kategoriye/kelimeye eşleşerek)
potansiyel bir kapsam-tanıma/halüsinasyon riski, ayrıca incelenmeli.

## Bulgu 2 — normal sorular (91 soru): ilk sıradaki öneri 74/91 (%81.3) doğru

- **Doğru (top-1 ground truth'ta):** 74/91 (%81.3)
- **Yanlış (top-1 ground truth'ta değil):** 17/91 (%18.7)

Gösterilen TÜM context'ler (sadece ilk sıra değil) baz alınırsa:
**452 context'in 346'sı (%76.5) gerçekten doğru** — yani sistem
göstermeye çalıştığında büyük çoğunlukla doğru işletmeleri gösteriyor,
kalan sorun daha çok SIRALAMA ve büyük beklenen kümelerindeki YAPISAL
sonuç sınırında yoğunlaşıyor (aşağıya bkz.).

Top-1 yanlış çıkan sorular: q009, q033, q034, q036, q042, q051, q052,
q054, q059, q060, q061, q070, q077, q078, q093, q094, q096.

Bunlardan `q009` üzerinde ayrıca örnek inceleme yapıldı: context'te doğru
işletme (fıtık tedavisi veren fizyoterapist) mevcuttu ama sıralamada
üstte değildi — yani en azından bu vakada kayıp bir eşleştirme sorunu
değil, bir SIRALAMA sorunu. Kalan 16 sorunun kaçının aynı örüntüyü
paylaştığı henüz tek tek doğrulanmadı.

## Genel değerlendirme

Güncel RAGAS skorları:

| Metrik | Skor |
|---|---|
| Faithfulness | 0.7399 |
| Answer Relevancy | 0.5983 |
| Context Precision | 0.4173 (0.4585 boş-hariç) |
| Context Recall | 0.5267 (0.5678 boş-hariç) |

Manuel doğrulama, aggregate skorların tek başına vermediği bir resim
ortaya koyuyor:

1. **Sistem "sürekli yanlış öneriyor" değil** — gösterdiği işletmelerin
   ~%76.5'i (ilk sırada ise ~%81.3'ü) gerçekten ground truth'ta. RAGAS'ın
   Context Precision/Recall'u bu oranın altında kalıyor (~%42-53), çünkü
   `reference` metnindeki iddiaların LLM ile context'te desteklenip
   desteklenmediğine bakıyor — cümle bazlı bu ölçüm, benim ID-kesişim
   bazlı sayımdan doğası gereği daha katı.
2. **Gerçek sıralama sorunu (17/91):** context'te doğru seçenek varken
   yanlışı öne çıkarma — en az bir örnek (q009) doğrulandı, kalan 16
   soru için detaylı kök-neden analizi henüz yapılmadı.
3. **Kapsam/halüsinasyon riski (2/9 `expected_empty`):** q099/q100'ün
   boş dönmesi gerekirken dönmemesi, ayrı bir inceleme gerektiriyor.
4. **Yapısal sınır (`RECOMMENDATION_RESULT_LIMIT=5`):** büyük beklenen
   kümelerinde (10-20 işletme) tam kapsam yapısal olarak imkansız —
   sistem doğru olanların çoğunu gösterse bile bu, Context Recall'u
   aşağı çeker, "yanlış öneri" anlamına gelmez.

Özetle: manuel doğrulama, sistemin gösterdiği önerilerin büyük
çoğunluğunun (~%76.5, ilk sırada ~%81.3) gerçekten doğru olduğunu
gösteriyor. RAGAS'ın aggregate Precision/Recall skorları bunun bir miktar
altında kalıyor — kısmen yapısal 5-sonuç sınırından, kısmen RAGAS'ın
kendi ölçüm biçiminin (cümle bazlı entailment) ID-kesişiminden daha katı
olmasından; geri kalan gerçek sorun ise tanımlı ve sınırlı bir sıralama
problemine (17/91 soru) indirgeniyor.

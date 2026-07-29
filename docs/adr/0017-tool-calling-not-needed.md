# ADR-0017: Tool calling gerekli değil — çoklu-hizmet arama ayrı bir projeye (SeekBind 2.0) bırakıldı

**Durum:** Kabul edildi
**Tarih:** 2026-07-29

## Bağlam

`docs/tech_stack.md` "Tool Calling"ı planlı bir teknoloji olarak listeliyordu,
roadmap'te de `feature/tool-calling` — "`tools.py` (calendar-service'i LLM'e
tool olarak sunar)" diye tanımlıydı. Ama bu kararın gerçek gerekçesi hiçbir
yerde yazılı değildi — sadece "gerekecek" varsayımıyla plana girmişti.

`feature/calendar-service`'in tasarımı konuşulurken (booking, müsaitlik
kontrolü, kullanıcının kendi randevularıyla çakışma kontrolü), şu soru
ortaya çıktı: bunların gerçekten hiçbiri, gerçek OpenAI Tool Calling
API'sini (ADR-0011/0014'ün bilinçli olarak kullanmadığı, `response_format=
json_object`'in aksine, LLM'in bir fonksiyonu ne zaman/nasıl çağıracağına
kendisinin karar verdiği mekanizma) gerektirmiyor gibi görünüyordu — hepsi
deterministik bir "kontrol et → sonuca göre eylem yap" akışına indirgenebilir
(bu kod tabanında zaten kullanılan `_rerank_businesses`'ın reranker
başarısız olunca RRF sırasını koruması, `_generate_recommendation_with_fallback`'ın
LLM başarısız olunca sabit mesaja düşmesi gibi if/else fallback deseniyle
aynı). Bunu varsaymak yerine gerçek LLM çağrılarıyla test etmeye karar
verildi (`research/tool-calling-edge-cases` branch'i).

## Yöntem

Gerçek bir işletme (LİVA BERBER, Berber kategorisi) kullanılarak, gerçek
`/recommend` akışına karşı 8 senaryo çalıştırıldı:

| # | Senaryo | Sonuç |
|---|---|---|
| 1 | İsimle işletme arama, başka kısıt yok | ✅ LİVA BERBER 1. sırada |
| 2 | İsim + geçerli gün/saat kısıtı | ✅ Gün/saat doğru ayrıştı, isim korundu |
| 3 | Var olmayan işletme adı | ✅ Uydurmadı, dürüstçe gerçek alternatiflere yönlendirdi |
| 4 | Çoklu kategori, aynı kısıt ("hem dişçi hem berber") | ⚠️ "Kazara" çalıştı — `category` null'a düşüyor, semantik arama şans eseri ikisini de üstte tutuyor, öneri metni ikisinden birer örnek seçiyor |
| 5 | Çoklu kategori + çelişkili fiyat ("ucuz dişçi ve pahalı berber") | ❌ **Gerçek kırılma** — pahalı bir dişçiyi "ucuz" diye sunup kendi "ama fiyatı yüksek" diyor, en ucuz berberi "pahalı ama uygun fiyatlı" diye tanımlıyor |
| 6 | İsim + kategori çelişkisi ("LİVA BERBER'den dişçi randevusu") | ✅ Çelişkiyi fark etti, doğru kategoriye yönlendirdi |
| 7 | Sadece işletme adı (bare) | ✅ Sorunsuz, isim yine 1. sırada |
| 8 | İsim + veri penceresi dışı gün | ⚠️ **Gerçek boşluk** — 0 sonuç, sadece genel "bulamadım" mesajı; "X'te yok ama alternatif var" davranışı yok |

## Değerlendirilen alternatifler

- **Tool calling'i planlandığı gibi uygulamak** (calendar-service'i LLM'e
  tool olarak sunmak): Reddedildi — 8 senaryonun 6'sı zaten mevcut
  `response_format=json_object` + deterministik kod deseniyle çözülüyor.
  Tool calling'in ayırt edici özelliği (bir adımın SONUCUNA göre sıradaki
  adıma karar vermek, örn. "salı müsait mi, değilse çarşambaya bak")
  bunların HİÇBİRİNDE gerekli değil — "müsait değilse alternatif ara"
  bile deterministik bir if/else, LLM'in karar vermesine gerek yok, çünkü
  doğru davranış (alternatif ara) her durumda aynı.
- **Çoklu-kategori desteğini SeekBind'in kendi şemasına eklemek** (senaryo
  5'in gerçek kırılmasını düzeltmek için): Şu an için reddedildi —
  `ParsedIntent`/`search_intent.txt`/`get_recommendation()`/`recommendation.txt`/
  API response şemasının hepsini yeniden tasarlamak gerekir
  (bkz. Sonuçlar), `feature/rag-pipeline`'ın kendisi kadar büyük bir iş.
  Bu ölçekte bir yeniden tasarımı SeekBind'in mevcut kapsamına sığdırmak
  yerine ayrı bir projeye taşımak tercih edildi.

## Karar

1. `feature/tool-calling` roadmap'ten kaldırıldı — SeekBind'in kendi
   mimarisi içinde gerçek tool calling'e ihtiyaç yok.
2. `feature/calendar-service` kalıyor, deterministik kalacak (booking,
   müsaitlik kontrolü, kullanıcı çakışma kontrolü) — ama müsait değilse
   alternatif önerisi, düz metne gömülü değil yapılandırılmış
   dönebilecek şekilde tasarlanması bir seçenek olarak not edildi (bkz.
   madde 3).
3. Senaryo 5'in ortaya çıkardığı çoklu-hizmet arama ihtiyacı, SeekBind'in
   kendi mimarisine eklenmeyecek — **ayrı bir proje** olarak ele
   alınacak: "SeekBind 2.0". Bu, SeekBind'i (bu proje, değiştirilmeden)
   dışarıdan bir mikroservis/HTTP servisi olarak çağıran, çoklu-hizmet ve
   günlük planlama yapabilen bir orkestrasyon katmanı olacak — burada
   gerçek tool calling haklı, çünkü SeekBind'e kaç kez, hangi
   parametrelerle çağrı yapılacağı (kaç farklı hizmet/işletme istendiği)
   önceden bilinmiyor, LLM'in kendisinin karar vermesi gerekiyor. Bu
   yüzden `feature/calendar-service`'in müsaitlik/alternatif çıktısının
   yapılandırılmış olması (madde 2) önemli — SeekBind 2.0'ın asıl
   tüketicisi zamanla insan değil, bu orkestrasyon katmanı olabilir.

## Sonuçlar

Ayrı repo, ayrı zaman çizelgesi — SeekBind 2.0 bu roadmap'in kapsamı
dışında, şimdilik sadece bir niyet notu. `docs/tech_stack.md`'deki "Tool
Calling" satırı da bu ADR'ye göre SeekBind'in kendisi için değil,
SeekBind 2.0 için geçerli sayılmalı.

`research/tool-calling-edge-cases` branch'inin ürettiği 8 gerçek smoke
test sonucu (`evaluation/results/diagnostics/rag_smoke_test/edge_*.json`)
kanıt olarak commit'lendi.

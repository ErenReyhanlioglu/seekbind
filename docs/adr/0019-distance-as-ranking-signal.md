# ADR-0019: Mesafe — filtre değil, RRF ile birleşen bir sıralama sinyali

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-30

## Bağlam

[ADR-0011](0011-hard-filter-vs-semantic-separation.md), konumu
("yakınımda") geocoding/cihaz konumu altyapısı olmadığı için bilinçli
olarak kapsam dışı bırakmıştı. [ADR-0018](0018-calendar-service-booking-and-alternatives.md)
calendar-service'in alternatif önerisini tasarlarken mesafeyi yine
aynı gerekçeyle ("şimdilik") ertelemiş, ayrı bir mini branch'e
(`feat/near-filter`) bırakmıştı.

Bu branch'in tetikleyicisi: gerçek geocoding hâlâ yok, ama
`UserProfile.latitude/longitude` (feat/user-profile'da eklenen referans
konum) zaten var ve kullanılmıyordu. Asıl karar verilmesi gereken soru
geocoding değildi — **mesafe bir FİLTRE mi olmalı, yoksa bir SIRALAMA
sinyali mi?** ve **birden fazla sinyal (puan + mesafe) aynı anda
istenirse ne olacak?**

## Değerlendirilen alternatifler

- **Mesafeyi Qdrant `geo_radius` ile katı bir filtre yapmak** (`NearFilter`'ın
  zaten var olan, hiç kullanılmayan tasarımı). Reddedildi: gerçek veride
  bazı kategoriler çok küçük (Cilt Bakım Merkezi 2 işletme, Noter 8
  işletme) — sabit bir yarıçap dışındaki tüm sonuçları elemek bu
  kategorilerde kolayca sıfır sonuca ("açlık") yol açar. `NearFilter`
  şeması ve `translate_filters_to_qdrant`'taki `geo_radius` çevirisi
  koda dokunulmadan bırakıldı (hâlâ hiçbir yerden set edilmiyor) — ayrı,
  gelecekte gerçek bir "X km içinde" katı filtre ihtiyacı çıkarsa diye
  duruyor, ama bu branch'in "yakınımda" davranışı onu KULLANMIYOR.
- **Yeni bir `distance_reference` parametresi yerine mevcut `SearchFilters.near`/`NearFilter`'ı
  kullanmak.** Reddedildi: `NearFilter` üçlüsü (lat, lon, radius_km) bir
  eşik/filtre kavramına bağlı (radius zorunlu alan) — sıralama amaçlı bir
  referans nokta için radius anlamsız bir zorunluluk olurdu. İki kavram
  (katı yarıçap filtresi vs. sıralama referans noktası) kasıtlı olarak
  ayrı tutuldu, aynı isim/tip altında karıştırılmadı.
- **Puan ve mesafeyi elle yazılmış bir "blend score" formülüyle
  birleştirmek.** Reddedildi — [ADR-0015](0015-rating-based-ranking-gap.md)
  ve [ADR-0018](0018-calendar-service-booking-and-alternatives.md)'de de
  aynı gerekçeyle reddedilmiş bir fikir: hangi ağırlıkla karıştırılacağı
  keyfi olur, gerçek veriyle kalibre edilmesi gerekir. Bunun yerine
  zaten var olan, BM25+vektör füzyonunda kullanılan `reciprocal_rank_fusion()`
  yeniden kullanıldı — **önemli ayrım:** ADR-0015'in reddettiği "puanı
  RRF'ye üçüncü bir sinyal olarak eklemek" alternatifi, puanı ALAKA
  (relevance, BM25+vektör) füzyonuna karıştırmayı reddediyordu — çünkü
  "en kötü" dendiğinde alakalı AMA düşük puanlı sonuç isteniyor, o füzyona
  karışırsa bozulur. Burada RRF'nin kullanımı bambaşka bir seviyede:
  cross-encoder reranking'den SONRA, yalnızca kullanıcının açıkça istediği
  iki tercih sinyali (puan sırası + mesafe sırası) arasında, alakaya hiç
  dokunmadan. Aynı fonksiyonun farklı bir amaçla ikinci kez kullanılması,
  ADR-0015'in kararını çelişkiye düşürmüyor.
- **`user_id`'yi opsiyonel yapmak** (anonim arama senaryosu). Reddedildi —
  SeekBind kişiselleştirilebilir bir öneri sistemi hedeflediği için
  aramanın her zaman bir kullanıcıya bağlı olması, ileride anonim/kayıtlı
  ayrımı gibi bir karmaşıklık eklemekten daha tutarlı bulundu (kullanıcı
  kararı — üretim sistemlerinde ikisi de yaygın, objektif tek doğru yok).

## Karar

1. **Mesafe her zaman bir SIRALAMA sinyali, asla bir eşik/filtre değil.**
   Yarıçap parametresi (radius_km gibi) hiçbir yerde kullanılmıyor —
   sort-not-filter kararının doğal bir sonucu, ayrıca bir "makul yarıçap
   ne olmalı" tartışmasına hiç gerek kalmadı.

2. **`search/service.py`:** `_sort_by_rating()` (private), rating VE mesafeyi
   birlikte ele alabilen `apply_final_sort()` (dışa açık) olarak
   genelleştirildi:
   - `_rank_by_rating()`: mevcut davranışın aynısı, ama artık TÜM
     işletmeleri (puansızlar dahil, sona eklenmiş) içeren sıralı bir
     `(id, 0.0)` listesi döner — RRF'e girdi olacak şekilde. Bu kritik:
     RRF bir listede HİÇ yer almayan id'yi sessizce eler, ama listenin
     SONUNA eklenmiş bir id'yi korur — tek sinyal aktifken davranış
     matematiksel olarak eskisiyle birebir aynı kalsın diye.
   - `_rank_by_distance()`: işletmeleri referans noktaya yakınlığa göre
     sıralar. Konumu olmayan (`latitude`/`longitude` NULL) işletmeler VE
     — `online_exempt_from_distance=True` iken — `online_available=True`
     olan işletmeler bu listeden tamamen çıkarılır (cezalandırılmaz/
     ödüllendirilmez, tıpkı puansız işletmelerin rating listesinde
     "sonda" ele alınması gibi).
   - `apply_final_sort()`: aktif sinyalleri (`rating_preference`,
     `distance_reference`) `reciprocal_rank_fusion()`'a listeler halinde
     verir. Tek sinyal varsa RRF tek liste üzerinde çalışıp o listenin
     sırasını aynen korur (eski tekil davranışa indirgenir). Hiçbir
     sinyale dahil olmayan işletmeler (ör. konumu yok VE puansız) en sona
     eklenir, sonuçtan asla düşmez.
   - `search_providers()`'a yeni `distance_reference: tuple[float, float] | None`
     parametresi eklendi; `_to_provider_result()` artık `distance_km`'i
     bu referanstan hesaplıyor (eski `NearFilter`/`filters.near` parametresi
     kaldırıldı — zaten hiçbir yerden set edilmiyordu, davranış kaybı yok).

3. **Online muafiyeti:** `online_available=True` olan işletmeler
   varsayılan olarak mesafe sıralamasından muaf — kullanıcı "yakınımda"
   dediğinde online bir hizmetin fiziksel mesafesi anlamsız. AMA kullanıcı
   AYRICA `online_only=True` istediyse (yani zaten sadece online işletme
   arıyorsa), muafiyet kalkar — `apply_final_sort(..., online_exempt_from_distance=not online_only)`.
   Gerçek smoke test'te bu ikinci dal (`online_only` + `near_me` birlikte)
   ayrı bir kablolama hatası olarak bulundu ve düzeltildi (bkz. Sonuçlar).

4. **Intent parsing** (`search_intent.txt`, `ParsedIntent.near_me: bool`):
   "yakınımda"/"civarımda" gibi kalıp ifadelerin YANINDA, "5 km uzaklıkta"
   gibi somut mesafe ifadeleri de `near_me=true`'ya çevrilir — sistemde
   ayrı bir yarıçap filtresi olmadığı için sayının kendisi hiçbir yerde
   kullanılmaz, sadece "bana yakın sırala" sinyaline indirgenir. Yer adları
   (`"İzmit'te"`) bu kurala GİRMEZ — farklı/belirli bir bölgeyi işaret
   eder, kullanıcının kendi konumuna yakınlıkla ilgisizdir, `semantic_query`'de
   kalır.

5. **`user_id` zorunlu:** `RecommendRequest.user_id: int` artık zorunlu
   alan. Tek somut kullanım yeri: `near_me=true` çıkarsa, `UserProfile`
   referans konumunu bulmak (`services/user_location.py` — hem `rag/service.py`
   hem `calendar.py` bu tek fonksiyonu kullanıyor, konum çözme mantığı iki
   yerde ayrı yazılmadı).

6. **`BookRequest.near_me: bool = False`:** mevcut `online_only`/`gender`/
   `min_price`/`max_price` opsiyonel-passthrough deseniyle birebir aynı —
   çağıran zaten `/recommend`'e yaptığı orijinal istekten bu tercihi
   biliyorsa iletebilir, yeni bir LLM çağrısı ya da altyapı gerekmedi.
   `calendar.py`'nin çapraz-işletme sıralaması da `apply_final_sort()`'u
   yeniden kullanacak şekilde güncellendi (kendi elle yazdığı rating-sort
   kodu silindi).

## Sonuçlar

`pytest`: 205 → 223 (18 yeni birim testi), `pyright`: 0 hata.

Gerçek LLM/DB/Qdrant'a karşı `smoke_test_rag.py`'ye 5 yeni senaryo
eklendi (16 → 21), `smoke_test_calendar.py`'ye 1 (ücretsiz, rollback'li).
Gerçek sonuçlar:

| Senaryo | Doğrulanan |
|---|---|
| "yakınımda ucuz bir berber" | `near_me=true`, sonuçlar saf mesafeye göre artan sırada (3.63→6.25 km) |
| "5 km uzaklıkta bir dişçi" | `near_me=true` (kural 4), mesafeye göre sıralı (1.17→1.68 km) |
| "İzmit'te bir dişçi" | `near_me=false` — yer adı doğru şekilde tetiklemedi, `distance_km` hepsi `None` |
| "yakınımda en iyi puanlı kuaför" | `near_me=true` + `rating_preference=high` birlikte; mesafeler artan sırada DEĞİL — RRF puan+mesafeyi gerçekten harmanlıyor, saf mesafe sıralaması değil |
| "yakınımda online bir ders" | `near_me=true` + `online_only=true`; dönen 5 sonucun hepsi `online_available=true` VE `distance_km` dolu, mesafeye göre sıralı — muafiyetin kalkması kablolamasının gerçek kanıtı |

**Bu branch'te bulunup düzeltilen bir kablolama hatası:** İlk uygulamada
hem `search_providers()` hem `calendar.py`, `apply_final_sort()`'u hep
varsayılan `online_exempt_from_distance=True` ile çağırıyordu —
`filters.online_only`/`online_only` parametresi hiç iletilmemişti. Yani
kullanıcı `online_only=True` + `near_me=True` istese bile online
işletmeler hep muaf kalıyordu (karar 3'ün ikinci yarısı uygulanmamıştı).
Smoke test senaryoları genişletilirken (online+near_me kombinasyonu
düşünülürken) fark edildi, kod ve testler düzeltildi.

Değişen dosyalar: `search/service.py`, `search/__init__.py`,
`search_intent.txt`, `rag/intent.py`, `rag/service.py`, `api/schemas.py`,
`api/routes.py`, `calendar.py`, yeni `services/user_location.py`,
`scripts/diagnostics/smoke_test_rag.py`, `scripts/diagnostics/smoke_test_calendar.py`.

**Bilinen sınırlar** (bilerek kapsam dışı):
- Gerçek geocoding/serbest metin adres çözümü hâlâ yok — referans konum
  her zaman `UserProfile`'ın sabit lat/lon'u, kullanıcının o an nerede
  olduğu ya da farklı bir adres belirtmesi desteklenmiyor.
- `NearFilter`/Qdrant `geo_radius` mekanizması koddan silinmedi ama hâlâ
  hiçbir yerden set edilmiyor — gerçek bir "X km içinde, kesin" filtre
  ihtiyacı çıkarsa diye dokunulmadan duruyor.

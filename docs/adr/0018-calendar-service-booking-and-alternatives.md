# ADR-0018: Calendar-service — rezervasyon, çakışma kontrolü ve alternatif önerisi

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-30

## Bağlam

[ADR-0017](0017-tool-calling-not-needed.md), calendar-service'in tool
calling gerektirmediğini, deterministik kodla çözülebileceğini
belirlemişti. Ama "deterministik kod" tek başına bir mimari değil —
somut olarak neyin nasıl kontrol edileceği, alternatif önerisinin nereden
geleceği, hangi kriterlere göre sıralanacağı gibi birçok soru bu branch'in
başında henüz kararlaştırılmamıştı. Bu ADR, o kararların hepsini tek
yerde topluyor.

## Değerlendirilen alternatifler

- **Alternatif önerisi için yeni bir "hangi işletmeler müsait" sorgusu
  yazmak.** Reddedildi — `search/availability.py`'deki
  `fetch_available_business_ids()` zaten bu soruyu (aday işletme kümesi +
  tarih/saat → müsait olanlar) çözüyor. Bu fonksiyon yeniden kullanıldı;
  yeni bir arama motoru icat edilmedi. Sonuç olarak calendar-service'in
  çapraz-işletme alternatif arama akışı, `search_providers()`'ın kendi
  iki fazlı deseninin (aday havuzu bul → müsaitliğe göre daralt) küçük
  ölçekli bir tekrarı oldu — sadece 1. faz Qdrant/BM25 yerine düz bir
  kategori+filtre sorgusu (semantik aramaya hiç gerek yok, çünkü
  belirsizlik yok: kategori ve tarih zaten kesin biliniyor).
- **Alternatifleri mesafeye göre de sıralamak/filtrelemek.** Reddedildi
  (şimdilik) — `UserProfile.latitude/longitude` referans konumu var ama
  kullanılmadı, bilinçli olarak ayrı bir mini branch'e
  (`feature/near-filter`, roadmap'te) bırakıldı. Ayrıca online
  hizmetlerde mesafenin hiç anlamı olmadığı (bkz. `online_available`)
  netleştirildi — mesafe ne zaman devreye girerse girsin, online
  işletmelerde uygulanmamalı.
- **Rating + mesafeyi tek bir "blend score"da birleştirmek.**
  Reddedilmiş bir fikir olarak akla geldi ama ADR-0015'teki aynı gerekçeyle
  (iki farklı sinyali karıştırmak yerine ya ayrı tutmak ya da net bir
  öncelik sırası kurmak) uygulanmadı.
- **`BookRequest`'e hazır `SearchFilters` gömmek.** Reddedildi —
  `RecommendRequest`'in de aynı sebeple yapmadığı gibi, `SearchFilters`
  burada anlamsız alanlar (`category`, `near`) taşırdı. Bunun yerine
  sadece ilgili 4 alan (`online_only`, `gender`, `min_price`, `max_price`)
  düz eklendi.
- **Alternatif aramasında kullanıcının orijinal (online/cinsiyet/fiyat)
  tercihlerini yeniden LLM'e sormak.** Gerekmedi — bu tercihler zaten
  `/recommend`'in intent parsing'inden geçmişti, çağıran taraf (bir
  frontend ya da SeekBind 2.0) bunları zaten elinde tutuyor ve `/book`
  isteğine düz veri olarak ekleyebilir. Yeni bir LLM çağrısı yok.

## Karar

**1. `book_appointment()` akışı** (`backend/services/calendar.py`):
slot var mı (yoksa `SlotNotFoundError` → HTTP 404) → slot zaten dolu mu
YA DA kullanıcının başka bir randevusuyla (appointment_duration_min
hesaba katılarak, farklı işletmeler dahil) çakışıyor mu → atomik
`UPDATE ... WHERE is_booked=false` ile rezerve etmeyi dene (iki isteğin
aynı slotu aynı anda kapması riskine karşı, ayrı bir SELECT+UPDATE'in
yarış penceresi yerine) → `Booking` kaydı oluştur.

**2. Alternatif önerisi iki kaynaktan gelir, birleştirilir:**
- *Aynı işletme, farklı zaman* — kronolojik sıralanır (puan sabit
  olduğu için sıralamada ayırt edici değil)
- *Aynı kategori, aynı gün müsait diğer işletmeler* —
  `fetch_available_business_ids()` ile bulunur, `weighted_rating`'e göre
  sıralanır (puanı olmayanlar `ADR-0015`'teki aynı desenle yön fark
  etmeksizin sona eklenir), her işletmeden sadece en erken boş slot alınır
  (çeşitlilik için)

Çapraz-işletme sonuçları önce gelir (birleştirilmiş listede), çünkü
orijinal istek genellikle günü sabit tutmak istiyor — sadece işletme
esnek. İkisi toplam `ALTERNATIVE_LIMIT=5`'e kadar kesilir.

**3. `BookRequest`** opsiyonel `online_only`/`gender`/`min_price`/`max_price`
alanları taşır — doluysa hem çapraz-işletme aday filtresine (kategori
eşleşmesinin yanı sıra) hem de dolaylı olarak sonuca yansır.

**4. Mesafe v1 kapsamı dışında** — `feature/near-filter`'a (roadmap)
bırakıldı, `UserProfile`'ın referans konumu o zaman kullanılacak.

## Sonuçlar

Gerçek DB'ye karşı hem elle hem `scripts/diagnostics/smoke_test_calendar.py`
ile doğrulandı (script, tek bir transaction içinde çalışıp sonunda
commit değil rollback yapıyor — tekrar tekrar çalıştırılabilir, kalıcı
sahte booking bırakmaz):

- **Başarılı rezervasyon**: gerçek bir slot rezerve edildi,
  `is_booked=true` ve `Booking` kaydı doğrulandı (DB'ye doğrudan sorguyla)
- **Slot başkası tarafından dolu**: reddedildi, 5 çapraz-işletme alternatifi
  `weighted_rating`'e göre kesin azalan sırada döndü (4.976 → 4.877 →
  4.864 → 4.855 → 4.853)
- **Kullanıcının farklı işletmedeki randevusuyla çakışma**: doğru tespit
  edildi (hatta ilk elle seçilen "boş" bir slot bile gerçekte bir
  çakışmaymış, sistem bunu insan gözünden önce yakaladı)
- **Fiyat filtresi**: `max_price` verildiğinde alternatif kümesi gerçekten
  değişti (daha ucuz işletmeler); çapraz-işletme adayları daraldığında
  kalan kapasite aynı işletmenin başka zamanlarıyla dolduruluyor
  (tasarlanan birleştirme mantığı doğrulandı)

30 yeni birim testi eklendi (205 toplam), pytest ve pyright temiz,
coverage %100 korundu.

**Bilinen sınırlar** (bilerek v1 dışı bırakıldı):
- `user_id`'nin gerçekten var olup olmadığı doğrulanmıyor — geçersiz bir
  `user_id` verilirse hata, DB'nin FK constraint'inden çıplak bir 500
  olarak sızıyor, kullanıcı dostu bir mesaj değil
- Mesafe (yukarıda açıklandı, `feature/near-filter`'a bırakıldı)

# ADR-0021: DB katmanının standartlara uygunluğunu kanıtlayan entegrasyon testleri

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-30

## Bağlam

`test/db-integration` (roadmap'te Faz 5), "gerçek Postgres'e karşı sorgu
testleri (N+1 kontrolü dahil — unit testteki mock'lu session gerçek sorgu
sayısını göremez)" olarak tanımlıydı. Branch'e girmeden önce
`backend/services/`, `backend/api/routes.py` ve `backend/db/models.py`'nin
8 ORM ilişkisi tek tek okunarak çıkarılan sonuç: **kod tabanında şu an hiçbir
yerde lazy relationship traversal yok** — her yerde açık `select(...).join(...)`
kullanılmış. Yani bu branch'e "muhtemelen bir N+1 bulup düzelteceğiz" diye
girilmedi; mevcut disiplini (proje kod standartlarının zaten emrettiği)
kanıtlanmış, regresyona karşı korumalı bir garantiye çevirmek asıl amaçtı —
bugün temiz olması, yarın bir refactor'ün bunu bozmayacağının garantisi değil.

Kapsam N+1'den geniş tutuldu: proje kod standartlarının "Veritabanı" bölümündeki her
madde (ham SQL yasağı, transaction yönetimi, index farkındalığı, ORM'in
response'a sızmaması, bulk yükleme, Repository katmanının bilinçli
yokluğu) tek tek değerlendirildi — bazıları zaten `test/api-integration`'da
dolaylı kanıtlanmıştı, bazıları mimari/statik kararlar olduğu için dinamik
test edilemez, ikisi (transaction rollback, index kullanımı) burada yeni
testlerle doğrudan kanıtlandı.

## Değerlendirilen alternatifler

- **`search_providers()`'ı da `book_appointment()` gibi throwaway veri +
  karşılaştırmalı (5 vs 50) sorgu sayısıyla test etmek.** Reddedildi —
  mekanik bir imkânsızlık: `search_providers()` Qdrant (vektör) ve BM25
  (ayrı bir session'dan kurulan in-memory index) üzerinden çalışıyor, ikisi
  de `savepoint_session`'ın commit edilmemiş throwaway verisini göremiyor
  (farklı bağlantı/session, transaction izolasyonu gereği). "5 vs 50
  throwaway işletme ekle" deseni burada hiçbir şeyi gerçekten kontrol
  etmiyordu. Bunun yerine `search_providers()`'ın DB'ye giden tek gerçek
  adımı (`_fetch_businesses_by_id`) doğrudan, gerçek (salt okunan, riski
  olmayan) dev veriyle test edildi — `book_appointment()`'ın alternatif
  bulma yolu ise tamamen session-tabanlı (Qdrant/BM25'e hiç dokunmuyor)
  olduğu için orada throwaway veri + karşılaştırmalı ölçüm sorunsuz çalıştı.
- **Tek noktalı bir üst sınır ("sorgu sayısı ≤ 3") ile yetinmek.** Reddedildi
  — bu, N+1'in *olmadığını* değil, o anki veri boyutu için bir üst sınırı
  kanıtlar; sıralı (non-concurrent) çalıştırılan naif bir implementasyon
  bile aynı sonucu verirdi. Bunun yerine her karşılaştırmalı test aynı
  fonksiyonu **iki farklı veri boyutunda** (5 vs 50) çalıştırıp sorgu
  sayısının **birebir eşit** çıktığını doğruluyor — sorgu sayısının veri
  boyutundan bağımsız (O(1)) olduğunun matematiksel kanıtı.
- **Transaction rollback testini de `savepoint_session` üzerinden yazmak.**
  Reddedildi — `savepoint_session`'ın kendisi zaten `get_db_session`'ın
  commit'ini SAVEPOINT'in arkasına gizliyor (bilerek, izolasyon için). Test
  ettiğimiz şey tam olarak `get_db_session`'ın rollback-on-exception
  davranışının kendisiyse, onu SAVEPOINT'in arkasında çalıştırmak asıl
  davranışı değil SAVEPOINT'in davranışını test etmiş olurdu. Bunun yerine
  `get_db_session()` gerçek bir async generator olarak elle sürüldü
  (`__anext__()`/`athrow()`), gerçek DB'ye karşı gerçek commit/rollback
  ile — kendi `try/finally` temizliğini yapıyor (bkz. `test_book_concurrency.py`'nin
  aynı ailesi: gerçek commit gerektiren testler kendi temizliğini kendi yapar).
- **Index kullanımını varsaymak.** Reddedilen bir kısayol — Postgres'in query
  planner'ı küçük tablolarda index yerine seq scan'i tercih edebilir. Bunun
  yerine gerçek dev veriye (`appointment_slots`, 32.504 satır) karşı
  `EXPLAIN (FORMAT JSON)` çalıştırılıp çıktı elle incelendi: gerçekten
  `"Index Only Scan"` + `"Index Name": "ix_slots_business_start_booked"`
  kullanıldığı görüldü, test bu gerçek kanıt üzerine yazıldı.

## Karar

1. **`query_counter` fixture'ı** (`tests/integration/conftest.py`) —
   `event.listen(engine.sync_engine, "before_cursor_execute", ...)` ile
   gerçek SQL sorgularını sayar. `AsyncEngine`'e doğrudan bağlanmak
   `NotImplementedError` fırlatır (`savepoint_session`'daki
   `session.sync_session` gotcha'sının aynı ailesi) — `.sync_engine`
   şart, gerçek dev DB'ye karşı doğrulandı. `SAVEPOINT`/`RELEASE SAVEPOINT`/
   `ROLLBACK TO SAVEPOINT` ifadeleri filtreleniyor (`savepoint_session`'ın
   kendi muhasebesi, gerçek uygulama sorgusu değil) — bu filtreleme de
   gerçek DB'ye karşı elle doğrulandı (3 ayrı senaryo: düz SELECT'ler,
   flush ile INSERT, commit ile SAVEPOINT döngüsü).
2. **`tests/integration/test_db_query_counts.py`** — 4 test:
   `_fetch_businesses_by_id` ve `fetch_available_business_ids` için "tam
   1 sorgu" (basit, tek satırlık sorgular), `resolve_price_threshold` için
   aynı, `book_appointment`'ın alternatif bulma yolu için 5 vs 50
   karşılaştırmalı (gerçek ölçüm: 7 == 7, `_fetch_slot` + çapraz-işletme
   4 sorgu + aynı-işletme 2 sorgu).
3. **`tests/integration/test_db.py`** — 2 test: `get_db_session`'ın gerçek
   rollback davranışı (yukarıda), `appointment_slots` bileşik index'inin
   gerçekten kullanıldığı (`EXPLAIN`, yukarıda).
4. **`tests/integration/factories.py`** (yeni) — throwaway `Business`/
   `AppointmentSlot`/`UserProfile` üreten yardımcı fonksiyonlar, `test_book.py`
   ile `test_db_query_counts.py` arasında paylaşılıyor (conftest.py'ye değil
   — bunlar fixture değil, düz yardımcı fonksiyon).

**Proje kod standartlarının "Veritabanı" bölümündeki diğer maddeler için kapsam kararı:**
ham SQL yasağı (zaten uyumlu, tek istisna `check_postgres`'teki kabul
edilmiş `SELECT 1`) ve ORM'in response'a sızmaması (`test/api-integration`'da
zaten dolaylı kanıtlandı) dinamik bir teste dönüştürülmedi — mükerrer ya da
gereksiz olurdu. Bulk upsert/truncate-and-load (`scripts/seed_db.py`) ve
Repository katmanının bilinçli yokluğu bilerek kapsam dışı bırakıldı — ilki
`backend/`'in canlı istek yolunda değil, ikincisi mimari bir karar, dinamik
test edilemez.

## Sonuçlar

`pytest -m integration`: 10 → 16 (6 yeni test), hepsi mevcut testlerle
birlikte tek oturumda da yeşil. `pytest`: 223 unit test regresyonsuz.
`pyright`: proje genelinde 0 hata. Tüm throwaway veri (SAVEPOINT-rollback
ya da gerçek commit + kendi temizliği) dev DB'de sıfır iz bıraktığı
doğrudan sorguyla teyit edildi.

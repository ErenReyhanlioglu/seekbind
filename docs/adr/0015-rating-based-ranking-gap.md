# ADR-0015: Puan/kalite bazlı sıralama — mimari bir eksiklik

**Durum:** Planlandı (sorun doğrulandı ve kayıt altına alındı, çözüm mimarisi henüz kararlaştırılmadı)
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

Henüz verilmedi. Çözüm mimarisi (örn. puanı RRF'ye üçüncü bir sinyal
olarak eklemek mi, ayrı bir "puana göre sırala" modu mu, yoksa post-hoc
bir yeniden sıralama/filtreleme mi) ayrı bir mini branch'te tasarlanıp
kararlaştırılacak. Bu ADR, sorunun gerçek veriyle doğrulanmış olduğunu
ve neden salt prompt değişikliğinin yeterli olmayacağını şimdiden kayıt
altına almak için yazıldı — mimari değişiklik sonrası gerekirse prompt
tarafına (örn. `recommendation.txt`'e puan uyuşmazlığı konusunda bir
dürüstlük kuralı eklemek) tekrar dönülebilir, ama o tek başına kök
nedeni çözmüyor.

## Sonuçlar

—

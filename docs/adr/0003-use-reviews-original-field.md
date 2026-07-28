# ADR-0003: `reviews_original` alanının kullanımı

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

SerpAPI'nin sayısal `reviews` alanı, Türkçe "B" (bin) eki içeren
büyük sayılarda (örn. "1,2 B") yanlış parse ediliyor.

## Karar

Orijinal string değer `reviews_original` alanında ayrıca saklanıyor
ve sayısal `reviews` alanından daha güvenilir kaynak olarak
kullanılıyor.

## Sonuçlar

Parse hatalarına karşı doğrulama/geri dönüş imkanı var — sayısal
alan şüpheli göründüğünde orijinal string'e bakılabiliyor.

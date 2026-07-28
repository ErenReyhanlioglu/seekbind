# ADR-0004: Bayesian düzeltmeli `weighted_rating`

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

Az yorumlu işletmeler (örn. 1 yorum, 5 yıldız) ham puan ortalamasıyla
sıralandığında, çok yorumlu ama biraz daha düşük puanlı işletmelere
göre yanıltıcı şekilde öne çıkabiliyor.

## Karar

Bayesian düzeltmeli bir `weighted_rating` alanı eklendi (yorum
sayısını da hesaba katan, genele yakınsayan bir düzeltme).

## Sonuçlar

Az yorumlu işletmelerin sıralamada haksız avantajı önleniyor;
sıralama/filtreleme mantığı ham `rating` yerine `weighted_rating`
kullanabiliyor.

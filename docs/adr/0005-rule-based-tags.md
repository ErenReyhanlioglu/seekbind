# ADR-0005: Kural tabanlı `tags` üretimi

**Durum:** Kabul edildi
**Tarih:** 2026-07-24

## Bağlam

İşletmelere nitelik etiketleri (`tags`) eklenmesi gerekiyordu. LLM
ile üretmek de bir seçenekti (`keywords` için yapıldığı gibi,
bkz. [ADR-0006](0006-llm-based-keywords.md)).

## Karar

`tags`, LLM ile değil kural tabanlı üretiliyor — yalnızca somut/
doğrulanabilir verilerden türetilen etiketler (online randevu,
hafta sonu açık, puan aralığı, fiyat aralığı gibi).

## Sonuçlar

Sübjektif/kanıtsız nitelikler ("yaşlı dostu", "samimi ortam" gibi)
bilerek üretilmiyor — halüsinasyon riski ortadan kalkıyor. Bunun
bedeli, `tags`'in `keywords`'e göre daha sınırlı/mekanik bir
etiket seti olması.

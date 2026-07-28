# ADR-0000: Mimari kararları ADR olarak kaydetme kararı

**Durum:** Kabul edildi
**Tarih:** 2026-07-28

## Bağlam

Proje boyunca alınan mimari kararlar (`gpt-4.1-mini` seçimi, hybrid
search tasarımı, reranker sağlayıcısı vb.) `docs/roadmap.md`'nin
sonunda tek bir "Önemli kararlar" başlığı altında madde madde
birikiyordu. Roadmap büyüdükçe bu bölüm de büyüdü ve iki farklı işi
aynı dosyada yapmaya başladı: "ne yapıldı/sırada ne var" (roadmap'in
asıl işi) ve "neden böyle yapıldı" (ayrı bir ihtiyaç). Bir kararın
bağlamını, değerlendirilen alternatifleri ve sonuçlarını bulmak için
tüm roadmap'i taramak gerekiyordu.

## Karar

Mimari kararlar artık `docs/adr/` altında, her biri kendi numaralı
Markdown dosyasında, ADR (Architecture Decision Record) formatında
tutulacak. `docs/roadmap.md` sadece faz/branch planına odaklanacak,
"Önemli kararlar" bölümü yerine `docs/adr/`'a kısa bir pointer
bırakacak.

Şablon: **Durum / Tarih / Bağlam / Karar / Sonuçlar** (gerektiğinde
"Değerlendirilen alternatifler" eklenir). Numaralandırma `0000`'dan
başlar, dosya isimleri İngilizce (topluluk konvansiyonu), içerik
Türkçe.

## Sonuçlar

- Roadmap'e taşınmış geçmiş kararlar (0001-0013), gerçek eklenme
  tarihleriyle (`git log -- docs/roadmap.md` üzerinden doğrulandı)
  buraya taşındı — tarih uydurulmadı.
- Bir karar değiştiğinde eski ADR silinmeyecek, yeni bir ADR onu
  supersede edecek (ilk örnek: [ADR-0013](0013-reranker-provider-selection.md),
  reranker sağlayıcısı kararının kendi içindeki revizyonu).
- Roadmap artık sadece "ne yapıldı" sorusuna, ADR'ler "neden"
  sorusuna cevap veriyor.

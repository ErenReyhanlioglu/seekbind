# ADR-0010: Hybrid search (BM25 + vektör, RRF)

**Durum:** Kabul edildi, uygulandı
**Tarih:** 2026-07-24 (karar) · 2026-07-27 (uygulandı — `feature/search-service`, PR #16)

## Bağlam

Ne salt BM25 (lexical) ne de salt semantic (vektör) arama tek başına
yeterli değil: BM25 tam kelime eşleşmesinde güçlü ama eş anlamlı/
örtük anlamlı sorgularda zayıf; semantic arama tam tersi — anlamı
yakalıyor ama tam eşleşmeyi bazen es geçebiliyor.

## Karar

BM25 ve semantic (Qdrant vektör) sonuçları Reciprocal Rank Fusion
(RRF, k=60) ile birleştiriliyor.

## Sonuçlar

`search-service` smoke testleriyle doğrulandı — kategori/niyet
sorgularında (örn. "boşanmak istiyorum avukat lazım") BM25 neredeyse
tamamen sessiz kaldığında bile RRF sayesinde vektör sonucu öne
çıkıyor ve doğru sonuç geliyor. Detaylı reranker öncesi/sonrası
kanıt için bkz. [ADR-0013](0013-reranker-provider-selection.md).

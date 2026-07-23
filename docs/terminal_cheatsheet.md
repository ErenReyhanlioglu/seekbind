# Terminal Komutları — Hızlı Referans

---

## Git — Günlük İş Akışı

Her yeni iş (feature/fix/docs) için izlenen sıra:

```
git checkout main
git pull                                   # main'i güncelle
git checkout -b feature/ozellik-adi        # yeni branch aç ve üzerine geç
# ... kod yazılır ...
git status                                 # ne değişti bak
git add dosya_adi.py                       # ya da: git add .
git commit -m "feat: kısa açıklama"        # Türkçe, conventional commit formatında
git push -u origin feature/ozellik-adi     # ilk push (upstream bağlar)
```

Sonraki push'larda `-u origin ...` gerekmez, sadece:
```
git push
```

GitHub'da PR açılıp `main`'e merge edildikten sonra:
```
git checkout main
git pull                                   # merge edilen değişiklikleri çek
git branch -d feature/ozellik-adi          # işi biten branch'i local'den sil
git push origin --delete feature/ozellik-adi   # remote'tan da sil (GitHub otomatik silmediyse)
```

### Yardımcı komutlar

| Komut | Ne işe yarar |
|---|---|
| `git status` | Değişen/yeni dosyaları gösterir |
| `git diff` | Değişikliklerin içeriğini satır satır gösterir |
| `git branch` | Var olan branch'leri listeler, `*` aktif olanı gösterir |
| `git branch -vv` | Branch'lerin hangi remote'a bağlı olduğunu da gösterir |
| `git checkout <branch>` | Başka bir branch'e geçer |
| `git log --oneline` | Commit geçmişini kısa özetle gösterir |
| `git merge main` | (feature branch'teyken) main'deki yeni değişiklikleri branch'ine getirir |
| `git fetch -p` | Remote'ta silinmiş branch referanslarını local'den temizler |

### Conventional Commit türleri (CLAUDE.md)

| Önek | Ne zaman kullanılır |
|---|---|
| `feat:` | Yeni özellik |
| `fix:` | Hata düzeltme |
| `refactor:` | Davranış değişmeden yeniden yapılandırma |
| `test:` | Test ekleme/güncelleme |
| `docs:` | Döküman güncelleme |
| `chore:` | Bağımlılık, iskelet, ayar gibi işler |

---

## uv — Python Ortam ve Bağımlılık Yönetimi

| Komut | Ne işe yarar |
|---|---|
| `uv --version` | Kurulu uv sürümünü gösterir |
| `uv init` | Yeni bir uv projesi başlatır (`pyproject.toml` oluşturur) |
| `uv sync` | `pyproject.toml`/`uv.lock`'a göre `.venv`'i kurar/günceller |
| `uv add <paket>` | Yeni bağımlılık ekler (örn. `uv add fastapi`) |
| `uv run <komut>` | Sanal ortamı aktive etmeden, o ortamdaki gibi komut çalıştırır |
| `uv run python -c "..."` | Tek satırlık Python kodu çalıştırır (hızlı test için) |

---

## Docker — Servisleri Yönetme

Proje kökünde `docker-compose.yml` ile PostgreSQL, Qdrant ve Langfuse (+ kendi DB'si) tanımlı.

| Komut | Ne işe yarar |
|---|---|
| `docker compose up -d` | Tüm servisleri arka planda başlatır |
| `docker compose ps` | Servislerin durumunu (çalışıyor/sağlıklı mı) gösterir |
| `docker compose logs <servis> --tail 40` | Bir servisin son loglarını gösterir (hata ayıklama için) |
| `docker compose restart <servis>` | Servisi yeniden başlatır (**.env değişikliğini okumaz!**) |
| `docker compose up -d --force-recreate <servis>` | Servisi sıfırdan oluşturur (**.env değişikliğinden sonra bunu kullan**) |
| `docker compose down` | Tüm servisleri durdurur ve container'ları siler (veriler volume'de kalır) |
| `docker compose down -v` | ⚠️ Container'ları **ve** volume'leri (yani tüm verileri) siler — dikkatli kullan |

### Önemli not
`.env` dosyasında bir değer değiştirdiğinde `restart` yetmez, çünkü environment değişkenleri container ilk oluşturulduğunda donuyor. Değişiklik sonrası mutlaka `--force-recreate` kullan ya da `docker compose up -d` ile tüm stack'i yeniden değerlendir.

### Proje servisleri ve portları

| Servis | Adres | Ne işe yarar |
|---|---|---|
| PostgreSQL (app) | `localhost:5432` | Uygulama verisi (sağlayıcılar, randevular vb.) |
| Qdrant | `localhost:6333` | Embedding'lerin tutulduğu vektör veritabanı |
| Langfuse | `localhost:3000` | LLM çağrılarının izlendiği web arayüzü |
| Langfuse DB | (dışarı açık değil) | Langfuse'un kendi iç verisi için ayrı Postgres |

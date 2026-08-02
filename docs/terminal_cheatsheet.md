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

### Conventional Commit türleri (proje kuralı)

| Önek | Ne zaman kullanılır |
|---|---|
| `feat:` | Yeni özellik |
| `fix:` | Hata düzeltme |
| `refactor:` | Davranış değişmeden yeniden yapılandırma |
| `test:` | Test ekleme/güncelleme |
| `docs:` | Döküman güncelleme |
| `chore:` | Bağımlılık, iskelet, ayar gibi işler |

### PowerShell'de çok satırlı commit mesajı

Bash heredoc (`git commit -m "$(cat <<'EOF' ... EOF)"`) PowerShell'de çalışmaz.
`git commit -m $msg` ve `$msg | git commit -F -` de kullanma — biri satırları
ayrı argümana bölüp pathspec hatası verir, diğeri Türkçe karakterleri (`ı`,
`ş`, `ğ` vb.) sessizce `?`'e çevirebilir. Doğru yöntem:

```powershell
$msg = @'
feat: kısa başlık

Uzun açıklama.
'@
# '@ kapanışı satır başında, boşluksuz olmalı

[System.IO.File]::WriteAllText("$PWD\commit_msg.txt", $msg, (New-Object System.Text.UTF8Encoding $false))
git commit -F commit_msg.txt
Remove-Item commit_msg.txt
```

(`Out-File -Encoding utf8` de olur ama BOM ekler — `WriteAllText` + `UTF8Encoding $false` temiz.)

---

## uv — Python Ortam ve Bağımlılık Yönetimi

| Komut | Ne işe yarar |
|---|---|
| `uv --version` | Kurulu uv sürümünü gösterir |
| `uv init` | Yeni bir uv projesi başlatır (`pyproject.toml` oluşturur) |
| `uv sync` | `pyproject.toml`/`uv.lock`'a göre `.venv`'i kurar/günceller |
| `uv add <paket>` | Yeni bağımlılık ekler (örn. `uv add fastapi`) |
| `uv add --group dev <paket>` | Sadece geliştirme/test için bağımlılık ekler (örn. `uv add --group dev httpx`) — üretime gitmez |
| `uv remove <paket>` | Bağımlılığı kaldırır (`--group dev` ile dev grubundan) |
| `uv run <komut>` | Sanal ortamı aktive etmeden, o ortamdaki gibi komut çalıştırır |
| `uv run python -c "..."` | Tek satırlık Python kodu çalıştırır (hızlı test için) |

---

## pytest — Test Çalıştırma

| Komut | Ne işe yarar |
|---|---|
| `uv run pytest` | Unit testleri çalıştırır (hızlı, mock'lu, docker gerektirmez) — `integration` marker'lı testler `pyproject.toml`'daki `addopts` ile varsayılan olarak hariç tutulur |
| `uv run pytest -m integration -v` | **Sadece** entegrasyon testlerini çalıştırır — gerçek Postgres/Qdrant'a bağlanır, önce `docker compose up -d` şart |
| `uv run pytest tests/integration/test_x.py -m integration -v` | Tek bir entegrasyon test dosyasını çalıştırır |
| `uv run pytest -k <isim_parçası>` | İsminde geçen kelimeye göre testleri filtreler (örn. `-k concurrency`) |
| `uv run pytest ... -s` | `print()` çıktısını gösterir (varsayılan davranış test çıktısını yutar) — hızlı debug için |
| `uv run pytest -q` | Sessiz mod, sadece özet (nokta nokta + son satır) |
| `uv run pyright` | Tip kontrolü — proje kuralı: her zaman 0 hata |

### Proje dışından (örn. scratchpad) tek seferlik bir Python betiği çalıştırma

Gerçek DB/Qdrant'a karşı hızlı bir kontrol/doğrulama yapmak için (kalıcı bir
teste dönüştürmeden) — `backend`/`scripts` importlarının bulunması için proje
kökü `PYTHONPATH`'e eklenmeli:

```
PYTHONPATH="<proje kökü>" uv run python "<betik yolu>"
```

Proje kökünden çalıştırılan `uv run python -c "..."` tek satırlıklarında buna gerek yok.

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
| Redis | `localhost:6379` | Embedding/LLM cache'i (`feature/cache-layer`) + rate limiting (`feature/middleware`) |
| Langfuse | `localhost:3000` | LLM çağrılarının izlendiği web arayüzü |
| Langfuse DB | (dışarı açık değil) | Langfuse'un kendi iç verisi için ayrı Postgres |

---

## CI'yi Push Etmeden Önce Lokalde Çalıştırma

`.github/workflows/ci.yml`'deki 5 job'ın lokal karşılıkları — push'tan önce
aynı kontrolleri kendi makinende çalıştırmak için:

| CI job | Lokal komut |
|---|---|
| **lint** | `uv run black --check .` ardından `uv run ruff check .` |
| **unit-test** | `uv run pytest --cov=backend --cov-report= --cov-fail-under=0` |
| **integration-test** | `uv run pytest -m "integration and not requires_ollama and not requires_seed_data" --cov=backend --cov-report= --cov-fail-under=0` |
| **coverage-report** | (unit + integration ayrı `COVERAGE_FILE` ile koşulduysa) `uv run coverage combine` ardından `uv run coverage report -m` |
| **build** | `docker build -f docker/Dockerfile.backend -t seekbind-backend:ci .` |

**Not:** lint ve build CI ile birebir aynı. Testlerde tek fark — CI,
entegrasyon testleri için tertemiz/boş bir Postgres kullanıyor (sadece
`business_types` seed'li), lokal `docker compose` stack'inde ise gerçek
478 işletme seed'li. Bu bir üst küme olduğu için testleri kırmaz, ama
CI'nin %100 birebir klonu değil — tam eşleşme istenirse `.env.ci`'deki
değerlerle ayrı/boş container'lar açmak gerekir.

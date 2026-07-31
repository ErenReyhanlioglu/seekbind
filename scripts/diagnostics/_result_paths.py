"""Diagnostic script'lerinin sonuç dosyalarını hangi LLM/embedder kombinasyonuna
göre klasörleyeceğini belirleyen ortak yardımcı.

Yapı: evaluation/results/diagnostics/<deney_türü>/<llm_model>/<embedder_model>/
LLM'e duyarlı olmayan script'ler (örn. search_smoke_test — search_providers()
hiç LLM çağırmıyor) `llm_model=None` verir, o katman hiç oluşmaz. Bu sayede
bir sonuç JSON'unun hangi kombinasyona ait olduğu dosya yolundan (içeriği
açmadan) anlaşılır — birden fazla LLM/embedder kombinasyonuyla karşılaştırma
yapıldığında (bkz. feature/fallback-mechanism sonrası mini ablasyon)
sonuçlar birbirine karışmaz.
"""

import re
from pathlib import Path

DIAGNOSTICS_ROOT: Path = Path("evaluation/results/diagnostics")
_SANITIZE_PATTERN: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def sanitize_model_name(model: str) -> str:
    """Model adını klasör adında güvenle kullanılabilecek bir parçaya çevirir.

    `backend.services.embedding._sanitize_model_tag` ile aynı mantık —
    burada ayrı tutulur çünkü bu modülün amacı (dosya sistemi klasörleme)
    oradakinden (Qdrant collection adı) farklı, kural tesadüfen aynı.
    """
    return _SANITIZE_PATTERN.sub("-", model.lower()).strip("-")


def build_results_dir(experiment_name: str, embedder_model: str, llm_model: str | None = None) -> Path:
    """`<deney_türü>/[<llm_model>/]<embedder_model>/` klasör yolunu üretir (oluşturmaz)."""
    path = DIAGNOSTICS_ROOT / experiment_name
    if llm_model is not None:
        path = path / sanitize_model_name(llm_model)
    return path / sanitize_model_name(embedder_model)

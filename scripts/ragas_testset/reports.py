"""`ragas_testset` analiz sonuçlarını zaman damgalı JSON olarak yazan ortak yardımcı.

`scripts/diagnostics/_result_paths.py` ile aynı desen: sonuç dosyası
`evaluation/results/diagnostics/ragas_testset/<analiz_adı>/<zaman
damgası>.json` yoluna yazılır. `payload` çağıran taraf zaten JSON'a
serileştirilebilir hale getirmiş olmalı (Pydantic modelleri için
`model_dump(mode="json")`) — burada `default=str` gibi bir kurtarma
mekanizması yok, sessizce yanlış bir serileştirme üretmesin diye.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

RESULTS_ROOT: Path = Path("evaluation/results/diagnostics/ragas_testset")


def write_report(analysis_name: str, payload: object) -> Path:
    """`<analiz_adı>/<zaman damgası>.json` yoluna rapor yazar, yazılan yolu döner."""
    directory = RESULTS_ROOT / analysis_name
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = directory / f"{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

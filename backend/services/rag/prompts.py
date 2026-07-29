"""RAG pipeline'ının prompt dosyalarını okuyan ortak yardımcı.

`intent.py` ve `recommendation.py` ikisi de `system.txt`'i (persona + gömülü
talimatlara karşı savunma notu) paylaştığı için dosya yolları ve okuma
mantığı tek bir yerde tutuluyor.
"""

from pathlib import Path

# __file__'a göre (proje köküne/CWD'ye göre değil) — uygulama farklı bir
# çalışma dizininden başlatılırsa (örn. Docker WORKDIR farklıysa) CWD-bağımlı
# bir yol kırılırdı, __file__ her zaman bu dosyanın gerçek konumunu verir.
PROMPT_DIR = Path(__file__).parent.parent.parent / "prompts"
SYSTEM_PROMPT_PATH = PROMPT_DIR / "system.txt"
SEARCH_INTENT_PROMPT_PATH = PROMPT_DIR / "search_intent.txt"
RECOMMENDATION_PROMPT_PATH = PROMPT_DIR / "recommendation.txt"


def load_prompt(path: Path) -> str:
    """Bir prompt dosyasını olduğu gibi (şablon yer tutucularıyla) okur."""
    return path.read_text(encoding="utf-8")

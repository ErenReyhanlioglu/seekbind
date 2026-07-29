"""RAG pipeline'ının prompt dosyalarını okuyan ortak yardımcı.

`intent.py` ve `recommendation.py` ikisi de `system.txt`'i (persona + gömülü
talimatlara karşı savunma notu) paylaştığı için dosya yolları ve okuma
mantığı tek bir yerde tutuluyor.
"""

from pathlib import Path

PROMPT_DIR = Path("backend/prompts")
SYSTEM_PROMPT_PATH = PROMPT_DIR / "system.txt"
SEARCH_INTENT_PROMPT_PATH = PROMPT_DIR / "search_intent.txt"
RECOMMENDATION_PROMPT_PATH = PROMPT_DIR / "recommendation.txt"


def load_prompt(path: Path) -> str:
    """Bir prompt dosyasını olduğu gibi (şablon yer tutucularıyla) okur."""
    return path.read_text(encoding="utf-8")

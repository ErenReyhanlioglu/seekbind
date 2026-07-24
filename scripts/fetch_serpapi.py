"""SerpAPI Google Local sonuçlarıyla İzmit/Kocaeli bölgesindeki işletme verisini çeker.

Her kategori için Türkçe sorgu atar, place_id'ye göre tekilleştirip
data/raw/businesses.jsonl dosyasına ekler. Script tekrar çalıştırıldığında
daha önce kaydedilmiş işletmeler tekrar yazılmaz.
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from serpapi import GoogleSearch

from backend.config import get_settings
from scripts.constants import CATEGORIES

logger = logging.getLogger(__name__)

SERPAPI_ENGINE: str = "google_local"
SERPAPI_LOCATION: str = "Kocaeli,Turkey"
SERPAPI_LANGUAGE: str = "tr"
GOOGLE_DOMAIN: str = "google.com"
OUTPUT_FILE_PATH: Path = Path("data/raw/businesses.jsonl")


class SerpApiRequestError(Exception):
    """SerpAPI isteği başarısız olduğunda ya da hata döndürdüğünde fırlatılır."""


class RawBusinessRecord(BaseModel):
    """data/raw/businesses.jsonl'a yazılan tek bir işletme kaydı."""

    place_id: str
    category_group: str
    query_term: str
    data: dict[str, Any]


def load_existing_place_ids(path: Path) -> set[str]:
    """Daha önce kaydedilmiş işletmelerin place_id'lerini okur."""
    if not path.exists():
        return set()
    place_ids: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            place_ids.add(record["place_id"])
    return place_ids


def build_query_tasks() -> list[tuple[str, str]]:
    """Kategori/terim kombinasyonlarını (grup, terim) listesine çevirir."""
    tasks: list[tuple[str, str]] = []
    for group, terms in CATEGORIES.items():
        for term in terms:
            tasks.append((group, term))
    return tasks


def fetch_local_results(query: str, api_key: str) -> list[dict[str, Any]]:
    """SerpAPI google_local motorundan ham local_results listesini döner."""
    params = {
        "engine": SERPAPI_ENGINE,
        "q": query,
        "location": SERPAPI_LOCATION,
        "google_domain": GOOGLE_DOMAIN,
        "hl": SERPAPI_LANGUAGE,
        "api_key": api_key,
    }
    search = GoogleSearch(params)
    payload = search.get_dict()
    if "error" in payload:
        raise SerpApiRequestError(f"SerpAPI hata döndürdü: {payload['error']}")
    return payload.get("local_results", [])


def collect_category(
    group: str,
    term: str,
    api_key: str,
    seen_place_ids: set[str],
) -> list[RawBusinessRecord]:
    """Bir kategori için sorgu atar, daha önce görülmemiş işletmeleri döner."""
    try:
        results = fetch_local_results(f"{term} izmit", api_key)
    except SerpApiRequestError as e:
        logger.warning("Sorgu atlandı: %s", e)
        return []

    new_records: list[RawBusinessRecord] = []
    for item in results:
        place_id = item.get("place_id")
        if not place_id or place_id in seen_place_ids:
            continue
        seen_place_ids.add(place_id)
        new_records.append(
            RawBusinessRecord(
                place_id=place_id,
                category_group=group,
                query_term=term,
                data=item,
            )
        )
    return new_records


def append_records(path: Path, records: list[RawBusinessRecord]) -> None:
    """Yeni kayıtları jsonl dosyasının sonuna ekler."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")


def main() -> None:
    """Tüm kategoriler için veri çeker ve data/raw/businesses.jsonl'a yazar."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    api_key = settings.serpapi_api_key.get_secret_value()

    seen_place_ids = load_existing_place_ids(OUTPUT_FILE_PATH)
    logger.info("Mevcut veri setinde %d işletme var", len(seen_place_ids))

    total_new = 0
    for group, term in build_query_tasks():
        new_records = collect_category(group, term, api_key, seen_place_ids)
        if new_records:
            append_records(OUTPUT_FILE_PATH, new_records)
            total_new += len(new_records)
        logger.info("%s -> %d yeni işletme", term, len(new_records))

    logger.info("Tamamlandı. Toplam yeni eklenen işletme: %d", total_new)


if __name__ == "__main__":
    main()

"""data/processed/businesses.jsonl'daki işletmelere LLM ile rich_description ekler.

generate_synthetic.py'nin ürettiği kural tabanlı alanlar (tip, hizmetler,
fiyat, süre, online durumu, cinsiyet) burada LLM'e context olarak verilir;
LLM'in tek işi bu bilgilerle tutarlı, doğal bir açıklama yazmaktır — başka
hiçbir alanı değiştirmez ya da uydurmaz. Sonuç, kaynak dosyanın üzerine
yazılmaz, ayrı bir dosyaya (OUTPUT_FILE_PATH) kaydedilir.
"""

import json
import logging
from pathlib import Path

from openai import APIError, APITimeoutError, OpenAI

from backend.config import get_settings
from scripts.schemas import ProcessedBusinessRecord

logger = logging.getLogger(__name__)

INPUT_FILE_PATH: Path = Path("data/processed/businesses.jsonl")
OUTPUT_FILE_PATH: Path = Path("data/processed/businesses_enriched.jsonl")
PROMPT_TEMPLATE_PATH: Path = Path("backend/prompts/synthetic_enrichment.txt")

LLM_TEMPERATURE: float = 0.7


class LLMEnrichmentError(Exception):
    """rich_description üretimi başarısız olduğunda fırlatılır."""


def load_prompt_template(path: Path) -> str:
    """Prompt şablonunu prompts/ klasöründen okur (koda gömülmez)."""
    return path.read_text(encoding="utf-8")


def load_processed_records(path: Path) -> list[ProcessedBusinessRecord]:
    """data/processed/businesses.jsonl'daki kayıtları okuyup doğrular."""
    records: list[ProcessedBusinessRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            records.append(ProcessedBusinessRecord(**json.loads(line)))
    return records


def write_records(path: Path, records: list[ProcessedBusinessRecord]) -> None:
    """Kayıtları jsonl olarak yeni bir dosyaya yazar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")


def build_prompt(record: ProcessedBusinessRecord, template: str) -> str:
    """Şablonu, işletmenin zaten belirlenmiş kural tabanlı alanlarıyla doldurur."""
    return template.format(
        title=record.title,
        type_normalized=record.type_normalized,
        services=", ".join(record.services),
        price_min=record.price_range_tl.min,
        price_max=record.price_range_tl.max,
        appointment_duration_min=record.appointment_duration_min,
        online_available="evet" if record.online_available else "hayır",
        gender=record.gender,
        rating=record.rating if record.rating is not None else "belirtilmemiş",
        reviews=record.reviews,
    )


def generate_rich_description(
    client: OpenAI,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> str:
    """OpenAI'den tek bir işletme için açıklama metni ister."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            timeout=timeout_seconds,
        )
    except APITimeoutError as e:
        raise LLMEnrichmentError("OpenAI isteği zaman aşımına uğradı") from e
    except APIError as e:
        raise LLMEnrichmentError(f"OpenAI API hatası: {e}") from e

    content = response.choices[0].message.content
    if not content:
        raise LLMEnrichmentError("OpenAI boş yanıt döndürdü")
    return content.strip()


def enrich_record(
    client: OpenAI,
    template: str,
    record: ProcessedBusinessRecord,
    model: str,
    timeout_seconds: int,
) -> ProcessedBusinessRecord:
    """Tek bir kaydı rich_description ile günceller, hata olursa değiştirmeden döner."""
    prompt = build_prompt(record, template)
    try:
        description = generate_rich_description(client, model, prompt, timeout_seconds)
    except LLMEnrichmentError as e:
        logger.warning("rich_description üretilemedi (place_id=%s): %s", record.place_id, e)
        return record
    return record.model_copy(update={"rich_description": description})


def main(limit: int | None = None) -> None:
    """Tüm (ya da limit kadar) kaydı LLM ile zenginleştirip yeni dosyaya yazar."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    template = load_prompt_template(PROMPT_TEMPLATE_PATH)

    records = load_processed_records(INPUT_FILE_PATH)
    if limit is not None:
        records = records[:limit]
    logger.info("%d kayıt zenginleştirilecek", len(records))

    enriched = [
        enrich_record(client, template, record, settings.openai_llm_model, settings.llm_call_timeout_seconds)
        for record in records
    ]

    write_records(OUTPUT_FILE_PATH, enriched)
    basarili = sum(1 for r in enriched if r.rich_description is not None)
    logger.info("Tamamlandı. %d/%d kayıt için açıklama üretildi -> %s", basarili, len(enriched), OUTPUT_FILE_PATH)


if __name__ == "__main__":
    main()

"""data/processed/businesses.jsonl'daki işletmelere LLM ile rich_description ve
keywords ekler.

generate_synthetic.py'nin ürettiği kural tabanlı alanlar (tip, hizmetler,
fiyat, süre, online durumu, cinsiyet) burada LLM'e context olarak verilir;
LLM'in tek işi bu bilgilerle tutarlı, doğal bir açıklama yazmaktır — başka
hiçbir alanı değiştirmez ya da uydurmaz. Aynı tipteki işletmeler küçük
gruplar (batch) halinde tek istekte gönderilir; hem daha az API çağrısı
hem de LLM'in aynı kalıbı tekrarlamak yerine işletmeler arasında gerçek
bir çeşitlilik üretmesi için. Sonuç, kaynak dosyanın üzerine yazılmaz,
ayrı bir dosyaya (OUTPUT_FILE_PATH) kaydedilir.
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
ENTRY_DELIMITER: str = "---BUSINESS---"

BATCH_SIZE: int = 6
LLM_TEMPERATURE: float = 0.8

GENDER_LABELS: dict[str, str] = {
    "female": "kadınlara yönelik",
    "male": "erkeklere yönelik",
    "unisex": "herkese açık",
}


class LLMEnrichmentError(Exception):
    """Bir batch için rich_description/keywords üretimi başarısız olduğunda fırlatılır."""


def load_prompt_template(path: Path) -> tuple[str, str]:
    """Prompt dosyasını header ve tek-işletme şablonu olarak ikiye ayırır."""
    content = path.read_text(encoding="utf-8")
    header_template, entry_template = content.split(ENTRY_DELIMITER, maxsplit=1)
    return header_template.strip(), entry_template.strip()


def load_processed_records(path: Path) -> list[ProcessedBusinessRecord]:
    """data/processed/businesses.jsonl'daki kayıtları okuyup doğrular."""
    records: list[ProcessedBusinessRecord] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            records.append(ProcessedBusinessRecord(**json.loads(line)))
    return records


def load_already_enriched(path: Path) -> dict[str, ProcessedBusinessRecord]:
    """Daha önce başarıyla zenginleştirilmiş (rich_description dolu) kayıtları okur.

    Yarıda kesilen bir çalıştırmadan sonra script tekrar başlatıldığında,
    zaten başarılı olan kayıtlar için tekrar API çağrısı yapıp para
    harcamamak amacıyla kullanılır.
    """
    if not path.exists():
        return {}
    enriched: dict[str, ProcessedBusinessRecord] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            record = ProcessedBusinessRecord(**json.loads(line))
            if record.rich_description is not None:
                enriched[record.place_id] = record
    return enriched


def write_records(path: Path, records: list[ProcessedBusinessRecord]) -> None:
    """Kayıtları jsonl olarak yeni bir dosyaya yazar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")


def group_into_batches(
    records: list[ProcessedBusinessRecord],
    batch_size: int,
    min_last_batch_size: int = 3,
) -> list[list[ProcessedBusinessRecord]]:
    """Kayıtları type_normalized'e göre gruplar, batch_size'lık parçalara böler.

    Son parça çok küçük kalırsa (min_last_batch_size'dan az), tek başına
    garip bir "N farklı işletme" ifadesi oluşturmasın diye bir önceki
    parçayla birleştirilir. Diğer parçalar batch_size'da kalır.
    """
    by_type: dict[str, list[ProcessedBusinessRecord]] = {}
    for record in records:
        by_type.setdefault(record.type_normalized, []).append(record)

    batches: list[list[ProcessedBusinessRecord]] = []
    for group in by_type.values():
        chunks = [group[i : i + batch_size] for i in range(0, len(group), batch_size)]
        if len(chunks) > 1 and len(chunks[-1]) < min_last_batch_size:
            chunks[-2].extend(chunks.pop())
        batches.extend(chunks)
    return batches


def build_batch_prompt(batch: list[ProcessedBusinessRecord], header_template: str, entry_template: str) -> str:
    """Header'ı bir kez, her işletme için entry şablonunu ayrı ayrı doldurup birleştirir."""
    header = header_template.format(count=len(batch), type_normalized=batch[0].type_normalized)
    entries = [
        entry_template.format(
            place_id=record.place_id,
            title=record.title,
            services=", ".join(record.services),
            price_min=record.price_range_tl.min,
            price_max=record.price_range_tl.max,
            appointment_duration_min=record.appointment_duration_min,
            online_text="online olarak da verilebiliyor" if record.online_available else "yüz yüze hizmet veriliyor",
            gender_text=GENDER_LABELS[record.gender],
            rating=record.rating if record.rating is not None else "Henüz değerlendirilmemiş",
            reviews=record.reviews,
        )
        for record in batch
    ]
    return header + "\n\n" + "\n\n".join(entries)


def call_llm_for_batch(client: OpenAI, model: str, prompt: str, timeout_seconds: int) -> list[dict]:
    """OpenAI'den bir batch için JSON sonuç listesi ister."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=LLM_TEMPERATURE,
            timeout=timeout_seconds,
            response_format={"type": "json_object"},
        )
    except APITimeoutError as e:
        raise LLMEnrichmentError("OpenAI isteği zaman aşımına uğradı") from e
    except APIError as e:
        raise LLMEnrichmentError(f"OpenAI API hatası: {e}") from e

    content = response.choices[0].message.content
    if not content:
        raise LLMEnrichmentError("OpenAI boş yanıt döndürdü")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMEnrichmentError("OpenAI yanıtı geçerli JSON değil") from e

    results = payload.get("results")
    if not isinstance(results, list):
        raise LLMEnrichmentError("Yanıtta 'results' listesi bulunamadı")
    return results


def enrich_batch(
    client: OpenAI,
    header_template: str,
    entry_template: str,
    batch: list[ProcessedBusinessRecord],
    model: str,
    timeout_seconds: int,
) -> list[ProcessedBusinessRecord]:
    """Bir batch'i zenginleştirir, hata olursa batch'i değiştirmeden döner."""
    prompt = build_batch_prompt(batch, header_template, entry_template)
    try:
        results = call_llm_for_batch(client, model, prompt, timeout_seconds)
    except LLMEnrichmentError as e:
        logger.warning("Batch başarısız (tip=%s, adet=%d): %s", batch[0].type_normalized, len(batch), e)
        return batch

    by_place_id = {r.get("place_id"): r for r in results if isinstance(r, dict)}
    enriched: list[ProcessedBusinessRecord] = []
    for record in batch:
        result = by_place_id.get(record.place_id)
        if result is None:
            logger.warning("place_id=%s batch yanıtında yok, atlandı", record.place_id)
            enriched.append(record)
            continue
        enriched.append(
            record.model_copy(
                update={
                    "rich_description": result.get("rich_description"),
                    "keywords": result.get("keywords", []),
                }
            )
        )
    return enriched


def main(limit: int | None = None) -> None:
    """Tüm (ya da limit kadar) kaydı batch'ler halinde LLM ile zenginleştirip yeni dosyaya yazar.

    Zaten zenginleştirilmiş kayıtlar atlanır, her batch sonrası dosya
    güncellenir — yarıda kesilirse tekrar çalıştırıldığında kaldığı
    yerden devam eder, başarılı batch'ler için tekrar para harcanmaz.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    header_template, entry_template = load_prompt_template(PROMPT_TEMPLATE_PATH)

    records = load_processed_records(INPUT_FILE_PATH)
    if limit is not None:
        records = records[:limit]

    already_enriched = load_already_enriched(OUTPUT_FILE_PATH)
    pending = [r for r in records if r.place_id not in already_enriched]
    logger.info(
        "%d kayıttan %d tanesi zaten zenginleştirilmiş, %d tanesi işlenecek",
        len(records),
        len(already_enriched),
        len(pending),
    )

    batches = group_into_batches(pending, BATCH_SIZE)
    logger.info("%d batch halinde işlenecek", len(batches))

    results: dict[str, ProcessedBusinessRecord] = dict(already_enriched)
    for i, batch in enumerate(batches, start=1):
        for record in enrich_batch(
            client, header_template, entry_template, batch, settings.openai_llm_model, settings.llm_call_timeout_seconds
        ):
            results[record.place_id] = record
        logger.info("Batch %d/%d tamamlandı (tip=%s, adet=%d)", i, len(batches), batch[0].type_normalized, len(batch))
        write_records(OUTPUT_FILE_PATH, [results.get(r.place_id, r) for r in records])

    basarili = sum(1 for r in results.values() if r.rich_description is not None)
    logger.info("Tamamlandı. %d/%d kayıt için açıklama üretildi -> %s", basarili, len(records), OUTPUT_FILE_PATH)


if __name__ == "__main__":
    main()

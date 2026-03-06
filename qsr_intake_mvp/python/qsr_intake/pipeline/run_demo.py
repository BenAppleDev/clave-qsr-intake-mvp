from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List

from qsr_intake.config import load_yaml
from qsr_intake.connectors.api_orders_connector import ApiOrdersConnector
from qsr_intake.connectors.csv_labor_connector import CsvLaborConnector
from qsr_intake.connectors.inventory_report_connector import InventoryReportConnector
from qsr_intake.normalization.normalizer import NormalizationContext, Normalizer
from qsr_intake.staging.parser import parse_raw_object
from qsr_intake.storage import LocalObjectStore
from qsr_intake.utils import stable_hash, utc_now_iso, write_jsonl


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = REPO_ROOT / "sample_data"
DEMO_DIR = REPO_ROOT / "demo_artifacts"


def _load_connectors() -> List[tuple[dict, object]]:
    configs = [
        (load_yaml(SAMPLE_DIR / "configs" / "api_orders_connector.yml"), ApiOrdersConnector()),
        (load_yaml(SAMPLE_DIR / "configs" / "csv_labor_connector.yml"), CsvLaborConnector()),
        (load_yaml(SAMPLE_DIR / "configs" / "inventory_report_connector.yml"), InventoryReportConnector()),
    ]
    fixed = []
    for config, connector in configs:
        sample_file = Path(config["sample_file"])
        if not sample_file.is_absolute():
            config["sample_file"] = str((REPO_ROOT / sample_file).resolve())
        fixed.append((config, connector))
    return fixed


def run_demo() -> Dict[str, List[dict]]:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    object_store = LocalObjectStore(DEMO_DIR / "object_storage")
    raw_batches: List[dict] = []
    raw_objects: List[dict] = []
    staged_records: List[dict] = []

    for config, connector in _load_connectors():
        window = {"window_start": config["schedule"]["window_start"], "window_end": config["schedule"]["window_end"]}
        batch_id = stable_hash([config["customer_id"], config["source_system"], config["name"], config["schedule"]["window_start"], config["schedule"]["window_end"]])[:16]
        config["batch_id"] = batch_id
        handles = connector.discover(window, config)
        batch_row = {
            "batch_id": batch_id,
            "customer_id": config["customer_id"],
            "source_system": config["source_system"],
            "source_family": config["source_family"],
            "connector_name": connector.connector_name,
            "connector_version": connector.connector_version,
            "config_version": str(config["version"]),
            "window_start": config["schedule"]["window_start"],
            "window_end": config["schedule"]["window_end"],
            "extracted_at": utc_now_iso(),
            "received_at": utc_now_iso(),
            "status": "completed",
        }
        raw_batches.append(batch_row)
        for sequence, handle in enumerate(handles, start=1):
            for envelope in connector.collect(handle, config):
                ext = "json" if envelope.content_type == "application/json" else "csv"
                object_key = f"raw/{config['customer_id']}/{config['source_system']}/{envelope.source_entity_type}/dt={config['schedule']['window_start'][:10]}/batch={batch_id}/obj={sequence}_{envelope.fingerprint}.{ext}"
                object_store.put_bytes(object_key, envelope.payload_bytes)
                raw_object_id = stable_hash([batch_id, object_key])
                raw_row = {
                    "raw_object_id": raw_object_id,
                    "batch_id": batch_id,
                    "customer_id": config["customer_id"],
                    "source_system": config["source_system"],
                    "source_family": envelope.source_family,
                    "source_entity_type": envelope.source_entity_type,
                    "source_location_id": envelope.source_location_id,
                    "source_object_id": envelope.source_object_id,
                    "source_object_observed_at": envelope.source_object_observed_at,
                    "object_key": object_key,
                    "content_type": envelope.content_type,
                    "byte_size": len(envelope.payload_bytes),
                    "sha256": stable_hash([envelope.payload_bytes.decode('utf-8')]),
                    "row_count_estimate": None,
                    "received_at": utc_now_iso(),
                    "inline_preview_jsonb": {},
                    "is_replay": False,
                    "original_raw_object_id": None,
                }
                raw_objects.append(raw_row)
                staged_records.extend(parse_raw_object(raw_row, envelope.payload_bytes))

    store_crosswalk = load_yaml(SAMPLE_DIR / "configs" / "store_crosswalks.yml")
    item_alias_doc = load_yaml(SAMPLE_DIR / "configs" / "item_aliases.yml")
    context = NormalizationContext(
        customer_id="clave-demo",
        store_crosswalk=store_crosswalk["stores"],
        item_aliases=item_alias_doc["items"],
    )
    normalizer = Normalizer(context)
    normalized = normalizer.normalize(staged_records)

    # Write outputs
    write_jsonl(DEMO_DIR / "raw" / "ingestion_batches.jsonl", raw_batches)
    write_jsonl(DEMO_DIR / "raw" / "raw_objects.jsonl", raw_objects)
    write_jsonl(DEMO_DIR / "staging" / "staged_records.jsonl", staged_records)
    for table_name, rows in normalized.items():
        target_dir = "derived" if table_name == "daily_store_metrics" else ("meta" if table_name == "record_metadata" else "canonical")
        write_jsonl(DEMO_DIR / target_dir / f"{table_name}.jsonl", rows)

    summary = {
        "raw_batches": len(raw_batches),
        "raw_objects": len(raw_objects),
        "staged_records": len(staged_records),
        "canonical_tables": {k: len(v) for k, v in normalized.items()},
    }
    (DEMO_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return normalized


if __name__ == "__main__":
    outputs = run_demo()
    print("Demo complete.")
    for key, rows in outputs.items():
        print(f"{key}: {len(rows)}")

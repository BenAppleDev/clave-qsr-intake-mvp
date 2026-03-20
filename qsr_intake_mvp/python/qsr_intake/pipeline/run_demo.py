from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List

from qsr_intake.bridge.local_bridge import LocalBridge
from qsr_intake.config import load_yaml
from qsr_intake.connectors.aloha_connector import AlohaIntegrationConnector
from qsr_intake.connectors.api_orders_connector import ApiOrdersConnector
from qsr_intake.connectors.csv_labor_connector import CsvLaborConnector
from qsr_intake.connectors.inventory_report_connector import InventoryReportConnector
from qsr_intake.normalization.normalizer import NormalizationContext, Normalizer
from qsr_intake.pipeline.landing import LandingArtifacts, build_batch_id
from qsr_intake.storage import LocalObjectStore
from qsr_intake.utils import write_jsonl


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = REPO_ROOT / "sample_data"
DEMO_DIR = REPO_ROOT / "demo_artifacts"


def run_demo(scenario: str = "core") -> Dict[str, List[dict]]:
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR, ignore_errors=True)

    landing = LandingArtifacts(object_store=LocalObjectStore(DEMO_DIR / "object_storage"))

    if scenario in {"core", "all"}:
        _run_core_demo(landing)
    if scenario in {"aloha_plan_a", "all"}:
        _run_aloha_plan_a(landing)
    if scenario in {"aloha_plan_b", "all"}:
        _run_aloha_plan_b(landing)

    normalized = _normalize_outputs(landing.staged_records)
    _write_outputs(landing, normalized, scenario)
    return normalized


def _run_core_demo(landing: LandingArtifacts) -> None:
    configs = [
        (load_yaml(SAMPLE_DIR / "configs" / "api_orders_connector.yml"), ApiOrdersConnector()),
        (load_yaml(SAMPLE_DIR / "configs" / "csv_labor_connector.yml"), CsvLaborConnector()),
        (load_yaml(SAMPLE_DIR / "configs" / "inventory_report_connector.yml"), InventoryReportConnector()),
    ]
    for config, connector in configs:
        if "sample_file" in config:
            config["sample_file"] = str(_resolve_path(config["sample_file"]))
        _run_connector_batch(landing, config, connector)


def _run_aloha_plan_a(landing: LandingArtifacts) -> None:
    config = load_yaml(SAMPLE_DIR / "configs" / "aloha_integration_connector.yml")
    config["params"]["sample_files"] = [str(_resolve_path(path)) for path in config["params"]["sample_files"]]
    _run_connector_batch(landing, config, AlohaIntegrationConnector())


def _run_aloha_plan_b(landing: LandingArtifacts) -> None:
    config = load_yaml(SAMPLE_DIR / "configs" / "aloha_local_bridge.yml")
    watch_dir = DEMO_DIR / "bridge_watch" / config["source_location_id"]
    checkpoint_path = DEMO_DIR / "checkpoints" / f"{config['name']}.json"
    config["params"]["watched_directory"] = str(watch_dir)
    config["params"]["checkpoint_path"] = str(checkpoint_path)

    watch_dir.mkdir(parents=True, exist_ok=True)
    _seed_watch_directory(SAMPLE_DIR / "raw" / "aloha" / "local_bridge" / "backfill", watch_dir)

    bridge = LocalBridge(config)

    config["batch_id"] = build_batch_id(config, "backfill")
    backfill_stats = bridge.run_backfill(lambda envelope: landing.land_envelope(config, envelope))
    landing.append_batch(
        config=config,
        connector_name=bridge.connector_name,
        connector_version=bridge.connector_version,
        window=backfill_stats["window"],
        status="completed" if not backfill_stats["failed_files"] else "completed_with_errors",
    )

    _seed_watch_directory(SAMPLE_DIR / "raw" / "aloha" / "local_bridge" / "live", watch_dir)

    config["batch_id"] = build_batch_id(config, "live")
    live_stats = bridge.run_live_iteration(lambda envelope: landing.land_envelope(config, envelope))
    landing.append_batch(
        config=config,
        connector_name=bridge.connector_name,
        connector_version=bridge.connector_version,
        window=live_stats["window"],
        status="completed" if not live_stats["failed_files"] else "completed_with_errors",
    )


def _run_connector_batch(landing: LandingArtifacts, config: dict, connector: object) -> None:
    window = {
        "window_start": config.get("schedule", {}).get("window_start"),
        "window_end": config.get("schedule", {}).get("window_end"),
    }
    config["batch_id"] = build_batch_id(config)
    landing.append_batch(
        config=config,
        connector_name=connector.connector_name,
        connector_version=connector.connector_version,
        window=window,
    )
    handles = connector.discover(window, config)
    for handle in handles:
        for envelope in connector.collect(handle, config):
            landing.land_envelope(config, envelope)


def _normalize_outputs(staged_records: List[dict]) -> Dict[str, List[dict]]:
    store_crosswalk = load_yaml(SAMPLE_DIR / "configs" / "store_crosswalks.yml")
    item_alias_doc = load_yaml(SAMPLE_DIR / "configs" / "item_aliases.yml")
    context = NormalizationContext(
        customer_id="clave-demo",
        store_crosswalk=store_crosswalk["stores"],
        item_aliases=item_alias_doc["items"],
    )
    normalizer = Normalizer(context)
    return normalizer.normalize(staged_records)


def _write_outputs(landing: LandingArtifacts, normalized: Dict[str, List[dict]], scenario: str) -> None:
    write_jsonl(DEMO_DIR / "raw" / "ingestion_batches.jsonl", landing.raw_batches)
    write_jsonl(DEMO_DIR / "raw" / "raw_objects.jsonl", landing.raw_objects)
    write_jsonl(DEMO_DIR / "staging" / "staged_records.jsonl", landing.staged_records)
    for table_name, rows in normalized.items():
        target_dir = "derived" if table_name == "daily_store_metrics" else ("meta" if table_name == "record_metadata" else "canonical")
        write_jsonl(DEMO_DIR / target_dir / f"{table_name}.jsonl", rows)

    summary = {
        "scenario": scenario,
        "raw_batches": len(landing.raw_batches),
        "raw_objects": len(landing.raw_objects),
        "staged_records": len(landing.staged_records),
        "canonical_tables": {key: len(value) for key, value in normalized.items()},
    }
    (DEMO_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _seed_watch_directory(source_dir: Path, watch_dir: Path) -> None:
    for path in sorted(source_dir.glob("*")):
        if path.is_file():
            shutil.copy2(path, watch_dir / path.name)


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the QSR intake MVP demo")
    parser.add_argument(
        "--scenario",
        choices=["core", "aloha_plan_a", "aloha_plan_b", "all"],
        default="core",
        help="Select which demo scenario to run",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    outputs = run_demo(args.scenario)
    print(f"Demo complete for scenario={args.scenario}.")
    for key, rows in outputs.items():
        print(f"{key}: {len(rows)}")

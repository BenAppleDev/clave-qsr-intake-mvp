from __future__ import annotations

import json
from pathlib import Path

from qsr_intake.normalization.resolver import EmbeddingProvider
import qsr_intake.pipeline.run_demo as run_demo_module
from qsr_intake.pipeline.run_demo import DEMO_DIR, REPO_ROOT, run_demo


class FakeEmbeddingProvider(EmbeddingProvider):
    provider_name = "fake"

    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        super().__init__(model_name)

    def encode(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if "burger" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "fries" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            elif "cola" in lowered:
                vectors.append([0.0, 0.0, 1.0])
            elif "patty" in lowered:
                vectors.append([1.0, 0.0, 1.0])
            elif "oil" in lowered:
                vectors.append([0.0, 1.0, 1.0])
            else:
                vectors.append([0.0, 0.0, 0.0])
        return __import__("numpy").asarray(vectors, dtype="float32")


def test_demo_runs_and_produces_outputs(monkeypatch):
    monkeypatch.setattr(run_demo_module, "SentenceTransformerEmbeddingProvider", FakeEmbeddingProvider)
    outputs = run_demo()
    assert len(outputs["orders"]) == 4
    assert len(outputs["checks"]) == 4
    assert len(outputs["line_items"]) == 6
    assert len(outputs["payments"]) == 4
    assert len(outputs["employees"]) == 2
    assert len(outputs["shift_actuals"]) == 2
    assert len(outputs["inventory_events"]) == 6
    assert len(outputs["record_metadata"]) == 28
    assert (DEMO_DIR / "summary.json").exists()


def test_core_demo_resolver_creates_match_review_and_unresolved_metadata(monkeypatch):
    monkeypatch.setattr(run_demo_module, "SentenceTransformerEmbeddingProvider", FakeEmbeddingProvider)
    run_demo("core")

    metadata_rows = _read_jsonl(DEMO_DIR / "meta" / "record_metadata.jsonl")
    resolver_rows = [
        row for row in metadata_rows if row["record_type"] in {"line_item", "inventory_event"}
    ]
    statuses = {(row["record_type"], row["normalization_exceptions"]["resolver"]["status"]) for row in resolver_rows}
    assert ("line_item", "matched") in statuses
    assert ("line_item", "review_required") in statuses
    assert ("line_item", "unresolved") in statuses
    assert ("inventory_event", "matched") in statuses
    assert ("inventory_event", "unresolved") in statuses

    rows_by_source = {
        row["normalization_exceptions"]["resolver"]["source_cleaned_name"]: row for row in resolver_rows
    }
    assert rows_by_source["fries"]["human_review_required"] is True
    assert rows_by_source["fries"]["human_review_status"] == "pending"
    assert rows_by_source["nebula slush"]["normalization_exceptions"]["resolver"]["chosen_key"] == "nebula_slush"
    assert rows_by_source["filter oil"]["normalization_exceptions"]["resolver"]["method"] == "store_override"
    assert rows_by_source["beef patty"]["entity_confidence_score"] >= 0.75

    line_items = _read_jsonl(DEMO_DIR / "canonical" / "line_items.jsonl")
    by_display = {row["display_name"]: row for row in line_items}
    assert by_display["Lrg Clsc Burg*r"]["normalized_item_key"] == "burger_classic"
    assert by_display["Fries??"]["normalized_item_key"] == "fries"
    assert by_display["Nebula Slush"]["normalized_item_key"] == "nebula_slush"

    inventory_rows = _read_jsonl(DEMO_DIR / "canonical" / "inventory_events.jsonl")
    by_code = {row["source_item_code"]: row for row in inventory_rows}
    assert by_code["CHI_INV_PAT"]["normalized_item_key"] == "burger_patty"
    assert by_code["LA_OIL_01"]["normalized_item_key"] == "fry_oil"
    assert by_code["LA_MYST_02"]["normalized_item_key"] == "kitchen_stardust"


def test_core_demo_preserves_raw_and_staging_payloads(monkeypatch):
    monkeypatch.setattr(run_demo_module, "SentenceTransformerEmbeddingProvider", FakeEmbeddingProvider)
    run_demo("core")

    raw_objects = _read_jsonl(DEMO_DIR / "raw" / "raw_objects.jsonl")
    sample_lookup = {
        "toast_orders_page_1.json": REPO_ROOT / "sample_data" / "raw" / "toast_orders_page_1.json",
        "toast_orders_page_2.json": REPO_ROOT / "sample_data" / "raw" / "toast_orders_page_2.json",
        "labor_timecards.csv": REPO_ROOT / "sample_data" / "raw" / "labor_timecards.csv",
        "inventory_report.csv": REPO_ROOT / "sample_data" / "raw" / "inventory_report.csv",
    }
    for row in raw_objects:
        landed_path = DEMO_DIR / "object_storage" / row["object_key"]
        assert landed_path.read_bytes() == sample_lookup[row["source_object_id"]].read_bytes()

    staged_records = _read_jsonl(DEMO_DIR / "staging" / "staged_records.jsonl")
    staged_names = {
        row["staged_payload"].get("display_name") or row["staged_payload"].get("source_item_name")
        for row in staged_records
    }
    assert "Lrg Clsc Burg*r" in staged_names
    assert "Fries??" in staged_names
    assert "Nebula Slush" in staged_names
    assert "Beef Pattie*" in staged_names
    assert "Kitchen Stardust" in staged_names


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

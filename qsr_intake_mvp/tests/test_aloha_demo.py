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


def test_aloha_plan_a_demo_end_to_end(monkeypatch):
    monkeypatch.setattr(run_demo_module, "SentenceTransformerEmbeddingProvider", FakeEmbeddingProvider)
    outputs = run_demo("aloha_plan_a")
    assert len(outputs["orders"]) == 3
    assert len(outputs["checks"]) == 3
    assert len(outputs["line_items"]) == 4
    assert len(outputs["payments"]) == 3
    assert len(outputs["record_metadata"]) == 13

    raw_objects = _read_jsonl(DEMO_DIR / "raw" / "raw_objects.jsonl")
    assert len(raw_objects) == 2
    assert {row["source_family"] for row in raw_objects} == {"aloha"}
    assert {row["source_mode"] for row in raw_objects} == {"integration_enabled"}

    staged_rows = _read_jsonl(DEMO_DIR / "staging" / "staged_records.jsonl")
    assert _counts_by(staged_rows, "source_entity_type") == {
        "order": 3,
        "check": 3,
        "line_item": 4,
        "payment": 3,
    }

    metadata_rows = _read_jsonl(DEMO_DIR / "meta" / "record_metadata.jsonl")
    assert {row["source_family"] for row in metadata_rows} == {"aloha"}
    assert {row["source_mode"] for row in metadata_rows} == {"integration_enabled"}

    for raw_row in raw_objects:
        sample_path = REPO_ROOT / "sample_data" / "raw" / "aloha" / "integration_enabled" / raw_row["source_object_id"]
        landed_path = DEMO_DIR / "object_storage" / raw_row["object_key"]
        assert landed_path.read_bytes() == sample_path.read_bytes()


def test_aloha_plan_b_demo_end_to_end(monkeypatch):
    monkeypatch.setattr(run_demo_module, "SentenceTransformerEmbeddingProvider", FakeEmbeddingProvider)
    outputs = run_demo("aloha_plan_b")
    assert len(outputs["orders"]) == 3
    assert len(outputs["checks"]) == 3
    assert len(outputs["line_items"]) == 4
    assert len(outputs["payments"]) == 3
    assert len(outputs["record_metadata"]) == 13

    batches = _read_jsonl(DEMO_DIR / "raw" / "ingestion_batches.jsonl")
    assert len(batches) == 2
    assert {row["source_mode"] for row in batches} == {"local_bridge_fallback"}

    raw_objects = _read_jsonl(DEMO_DIR / "raw" / "raw_objects.jsonl")
    assert len(raw_objects) == 6
    assert {row["source_family"] for row in raw_objects} == {"aloha"}
    assert {row["source_mode"] for row in raw_objects} == {"local_bridge_fallback"}

    staged_rows = _read_jsonl(DEMO_DIR / "staging" / "staged_records.jsonl")
    assert _counts_by(staged_rows, "source_entity_type") == {
        "order": 3,
        "check": 3,
        "line_item": 4,
        "payment": 3,
    }

    metadata_rows = _read_jsonl(DEMO_DIR / "meta" / "record_metadata.jsonl")
    assert {row["source_family"] for row in metadata_rows} == {"aloha"}
    assert {row["source_mode"] for row in metadata_rows} == {"local_bridge_fallback"}

    sample_lookup = {}
    for base in [
        REPO_ROOT / "sample_data" / "raw" / "aloha" / "local_bridge" / "backfill",
        REPO_ROOT / "sample_data" / "raw" / "aloha" / "local_bridge" / "live",
    ]:
        for path in base.glob("*.csv"):
            sample_lookup[path.name] = path

    for raw_row in raw_objects:
        landed_path = DEMO_DIR / "object_storage" / raw_row["object_key"]
        assert landed_path.read_bytes() == sample_lookup[Path(raw_row["source_object_id"]).name].read_bytes()


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _counts_by(rows: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row[key]] = counts.get(row[key], 0) + 1
    return counts

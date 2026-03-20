from __future__ import annotations

import json
from pathlib import Path

from qsr_intake.bridge.local_bridge import LocalBridge


def test_local_bridge_checkpoint_resume(tmp_path):
    config = _bridge_config(tmp_path)
    _write_file(tmp_path / "watch" / "checks_2026-03-04.csv", "check export")
    _write_file(tmp_path / "watch" / "items_2026-03-04.csv", "item export")
    _write_file(tmp_path / "watch" / "payments_2026-03-04.csv", "payment export")

    bridge = LocalBridge(config)
    uploads: list[str] = []
    should_fail = {"payments_2026-03-04.csv": True}

    def upload(envelope):
        file_name = Path(envelope.source_object_id).name
        if should_fail.get(file_name):
            should_fail[file_name] = False
            raise RuntimeError("simulated upload failure")
        uploads.append(file_name)

    first = bridge.run_backfill(upload)
    assert sorted(first["uploaded_files"]) == ["checks_2026-03-04.csv", "items_2026-03-04.csv"]
    assert first["failed_files"] == ["payments_2026-03-04.csv"]

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert sorted(checkpoint["processed"]) == ["checks_2026-03-04.csv", "items_2026-03-04.csv"]
    assert "payments_2026-03-04.csv" in checkpoint["failures"]

    second = LocalBridge(config).run_backfill(upload)
    assert second["uploaded_files"] == ["payments_2026-03-04.csv"]
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert sorted(checkpoint["processed"]) == [
        "checks_2026-03-04.csv",
        "items_2026-03-04.csv",
        "payments_2026-03-04.csv",
    ]
    assert checkpoint["failures"] == {}


def test_local_bridge_backfill_chunking_by_day(tmp_path):
    config = _bridge_config(tmp_path, backfill_chunk_size=1, backfill_chunk_by="day")
    _write_file(tmp_path / "watch" / "checks_2026-03-04.csv", "day1 checks")
    _write_file(tmp_path / "watch" / "items_2026-03-04.csv", "day1 items")
    _write_file(tmp_path / "watch" / "checks_2026-03-05.csv", "day2 checks")

    bridge = LocalBridge(config)
    uploads: list[str] = []
    stats = bridge.run_backfill(lambda envelope: uploads.append(Path(envelope.source_object_id).name))

    assert stats["chunks_processed"] == 2
    assert stats["chunk_keys"] == ["2026-03-04", "2026-03-05"]
    assert uploads == ["checks_2026-03-04.csv", "items_2026-03-04.csv", "checks_2026-03-05.csv"]


def test_local_bridge_live_mode_only_picks_up_new_files(tmp_path):
    config = _bridge_config(tmp_path)
    _write_file(tmp_path / "watch" / "checks_2026-03-04.csv", "day1 checks")

    bridge = LocalBridge(config)
    uploads: list[str] = []

    first = bridge.run_live_iteration(lambda envelope: uploads.append(Path(envelope.source_object_id).name))
    assert first["uploaded_files"] == ["checks_2026-03-04.csv"]

    second = bridge.run_live_iteration(lambda envelope: uploads.append(Path(envelope.source_object_id).name))
    assert second["uploaded_files"] == []

    _write_file(tmp_path / "watch" / "items_2026-03-05.csv", "day2 items")
    third = bridge.run_live_iteration(lambda envelope: uploads.append(Path(envelope.source_object_id).name))
    assert third["uploaded_files"] == ["items_2026-03-05.csv"]
    assert uploads == ["checks_2026-03-04.csv", "items_2026-03-05.csv"]


def test_local_bridge_retries_transient_failures(tmp_path):
    config = _bridge_config(tmp_path, max_retries=1)
    _write_file(tmp_path / "watch" / "checks_2026-03-04.csv", "day1 checks")

    attempts = {"count": 0}

    def upload(_envelope):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient failure")

    stats = LocalBridge(config).run_backfill(upload)
    assert attempts["count"] == 2
    assert stats["uploaded_files"] == ["checks_2026-03-04.csv"]
    assert stats["failed_files"] == []


def _bridge_config(tmp_path, *, backfill_chunk_size: int = 2, backfill_chunk_by: str = "file", max_retries: int = 0):
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    return {
        "name": "bridge_test",
        "version": "v1",
        "customer_id": "clave-demo",
        "source_system": "aloha_local_exports",
        "source_family": "aloha",
        "source_mode": "local_bridge_fallback",
        "source_location_id": "aloha-hou-001",
        "batch_id": "bridge-batch",
        "params": {
            "watched_directory": str(watch_dir),
            "checkpoint_path": str(tmp_path / "checkpoint.json"),
            "file_specs": [
                {"source_entity_type": "aloha_checks_export", "file_glob": "checks_*.csv"},
                {"source_entity_type": "aloha_items_export", "file_glob": "items_*.csv"},
                {"source_entity_type": "aloha_payments_export", "file_glob": "payments_*.csv"},
            ],
            "polling_interval_seconds": 0,
            "backfill_chunk_size": backfill_chunk_size,
            "backfill_chunk_by": backfill_chunk_by,
            "throttle_seconds": 0,
            "retry_backoff_seconds": 0,
            "max_retries": max_retries,
            "timezone": "America/Chicago",
            "max_files_per_live_scan": 10,
        },
    }


def _write_file(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")

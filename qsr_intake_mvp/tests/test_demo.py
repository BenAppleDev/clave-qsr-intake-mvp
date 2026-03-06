from __future__ import annotations

from pathlib import Path

from qsr_intake.pipeline.run_demo import run_demo, DEMO_DIR


def test_demo_runs_and_produces_outputs():
    outputs = run_demo()
    assert len(outputs["orders"]) == 2
    assert len(outputs["checks"]) == 2
    assert len(outputs["line_items"]) == 3
    assert len(outputs["payments"]) == 2
    assert len(outputs["employees"]) == 2
    assert len(outputs["shift_actuals"]) == 2
    assert len(outputs["inventory_events"]) == 3
    assert len(outputs["record_metadata"]) >= 14
    assert (DEMO_DIR / "summary.json").exists()

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "demo_artifacts"


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL must be set to load demo outputs into PostgreSQL")

    files = {
        "raw.ingestion_batches": DEMO_DIR / "raw" / "ingestion_batches.jsonl",
        "raw.raw_objects": DEMO_DIR / "raw" / "raw_objects.jsonl",
        "staging.staged_records": DEMO_DIR / "staging" / "staged_records.jsonl",
        "canonical.stores": DEMO_DIR / "canonical" / "stores.jsonl",
        "canonical.business_days": DEMO_DIR / "canonical" / "business_days.jsonl",
        "canonical.orders": DEMO_DIR / "canonical" / "orders.jsonl",
        "canonical.checks": DEMO_DIR / "canonical" / "checks.jsonl",
        "canonical.line_items": DEMO_DIR / "canonical" / "line_items.jsonl",
        "canonical.payments": DEMO_DIR / "canonical" / "payments.jsonl",
        "canonical.employees": DEMO_DIR / "canonical" / "employees.jsonl",
        "canonical.shift_actuals": DEMO_DIR / "canonical" / "shift_actuals.jsonl",
        "canonical.inventory_events": DEMO_DIR / "canonical" / "inventory_events.jsonl",
        "meta.record_metadata": DEMO_DIR / "meta" / "record_metadata.jsonl",
        "derived.daily_store_metrics": DEMO_DIR / "derived" / "daily_store_metrics.jsonl",
    }

    with psycopg.connect(dsn) as conn:
        for table, path in files.items():
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join(["%s"] * len(cols))
            column_sql = ", ".join(cols)
            update_sql = ", ".join(
                f"{col}=EXCLUDED.{col}" for col in cols if col not in {"batch_id", "raw_object_id", "staged_record_id", "store_id", "business_day_id", "order_id", "check_id", "line_item_id", "payment_id", "employee_id", "shift_actual_id", "inventory_event_id", "record_uid", "daily_store_metrics_id"}
            )
            # Best-effort upsert; production code would use table-specific keys.
            first_pk = cols[0]
            sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) ON CONFLICT ({first_pk}) DO UPDATE SET {update_sql};"
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(sql, [row[col] for col in cols])
        conn.commit()
    print("Loaded demo outputs into PostgreSQL.")


if __name__ == "__main__":
    main()

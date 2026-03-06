from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "demo_artifacts"


def adapt_value(value):
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


def ensure_normalization_runs(conn, files):
    # Map run_id -> customer_id
    runs: dict[str, str] = {}

    for path in [
        dict(files).get("meta.record_metadata"),
        dict(files).get("derived.daily_store_metrics"),
    ]:
        if not path or not path.exists():
            continue

        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue

                row = json.loads(line)
                run_id = row.get("normalization_run_id") or row.get("derived_from_run_id")
                customer_id = row.get("customer_id")

                if run_id:
                    runs[run_id] = customer_id or "clave-demo"

    if not runs:
        return

    with conn.cursor() as cur:
        for run_id, customer_id in runs.items():
            cur.execute(
                """
                INSERT INTO ops.normalization_runs
                    (normalization_run_id, customer_id, started_at, completed_at, status)
                VALUES
                    (%s, %s, NOW(), NOW(), 'completed')
                ON CONFLICT (normalization_run_id) DO NOTHING
                """,
                [run_id, customer_id],
            )


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL must be set to load demo outputs into PostgreSQL")

    files = [
        ("raw.ingestion_batches", DEMO_DIR / "raw" / "ingestion_batches.jsonl"),
        ("raw.raw_objects", DEMO_DIR / "raw" / "raw_objects.jsonl"),
        ("staging.staged_records", DEMO_DIR / "staging" / "staged_records.jsonl"),
        ("canonical.stores", DEMO_DIR / "canonical" / "stores.jsonl"),
        ("canonical.business_days", DEMO_DIR / "canonical" / "business_days.jsonl"),
        ("canonical.orders", DEMO_DIR / "canonical" / "orders.jsonl"),
        ("canonical.checks", DEMO_DIR / "canonical" / "checks.jsonl"),
        ("canonical.line_items", DEMO_DIR / "canonical" / "line_items.jsonl"),
        ("canonical.payments", DEMO_DIR / "canonical" / "payments.jsonl"),
        ("canonical.employees", DEMO_DIR / "canonical" / "employees.jsonl"),
        ("canonical.shift_actuals", DEMO_DIR / "canonical" / "shift_actuals.jsonl"),
        ("canonical.inventory_events", DEMO_DIR / "canonical" / "inventory_events.jsonl"),
        ("meta.record_metadata", DEMO_DIR / "meta" / "record_metadata.jsonl"),
        ("derived.daily_store_metrics", DEMO_DIR / "derived" / "daily_store_metrics.jsonl"),
    ]

    with psycopg.connect(dsn) as conn:
        ensure_normalization_runs(conn, files)

        for table, path in files:
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
                f"{col}=EXCLUDED.{col}"
                for col in cols
                if col
                not in {
                    "batch_id",
                    "raw_object_id",
                    "staged_record_id",
                    "store_id",
                    "business_day_id",
                    "order_id",
                    "check_id",
                    "line_item_id",
                    "payment_id",
                    "employee_id",
                    "shift_actual_id",
                    "inventory_event_id",
                    "record_uid",
                    "daily_store_metrics_id",
                    "normalization_run_id",
                }
            )

            first_pk = cols[0]
            sql = f"""
                INSERT INTO {table} ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT ({first_pk}) DO UPDATE SET {update_sql};
            """

            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(sql, [adapt_value(row[col]) for col in cols])

        conn.commit()

    print("Loaded demo outputs into PostgreSQL.")


if __name__ == "__main__":
    main()
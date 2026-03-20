# QSR Intake MVP

A concrete MVP scaffold for a QSR data ingestion, normalization, and trust layer.

This repo implements a **batch-first** intake pipeline for **POS + labor + inventory** data with:

- reusable connector families
- immutable raw landing in object storage
- thin staging records
- canonical PostgreSQL schema
- first-class provenance / freshness / quality / confidence metadata
- sample datasets and a runnable local demo

## What is included

- **C++ runtime scaffold** for long-running connector hosting and edge-agent style execution
- **Python connectors + workers** for fast MVP iteration
- **PostgreSQL DDL** for raw, staging, canonical, meta, config, ops, and derived layers
- **Sample configs** for an API orders feed, a labor CSV feed, and an inventory report feed
- **Sample datasets** that demonstrate the pipeline end-to-end
- **Demo runner** that ingests sample data and writes raw, staged, canonical, metadata, and derived outputs

## Quick start

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo
```

Aloha demos:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_a
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_b
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario all
```

Outputs are written to:

```text
demo_artifacts/
  raw/
  staging/
  canonical/
  meta/
  derived/
  object_storage/
```

## Aloha source family

This MVP models Aloha as one source family with two operating modes:

- `integration_enabled`: a structured local integration surface exists and a collector polls that surface.
- `local_bridge_fallback`: no practical integration surface exists, so a dumb back-office bridge uploads raw export/report files.

Both modes land immutable raw payloads and feed the same staging, normalization, canonical, metadata, and derived paths. The edge changes; the central pipeline does not.

The local bridge is intentionally narrow. It only:

- discovers local files
- packages raw bytes
- uploads with retry
- checkpoints progress
- reports simple health

It does not normalize business entities or interpret restaurant semantics. That work stays in staging and normalization workers.

## Optional: load into PostgreSQL

1. Create a database.
2. Apply SQL in `sql/migrations/`.
3. Export `DATABASE_URL`.
4. Run:

```bash
python -m qsr_intake.pipeline.load_to_postgres
```

## Important implementation choices

This scaffold intentionally tightens the earlier design:

- `raw.ingestion_batches` is the single source of truth for batch metadata.
- Record-level trust metadata is consolidated into `meta.record_metadata`.
- `derived.daily_store_metrics` is treated as derived output, not raw truth.
- `canonical.adjustments` exists as an optional compatibility table but is not required by the demo path.
- C++ is used for the runtime spine and edge-agent scaffolding; Python is used for most early connectors and all transformation work.

## Repo map

```text
cpp/
  connector_runtime/
docs/
python/
  qsr_intake/
sample_data/
sql/
tests/
```

See `docs/IMPLEMENTATION_SCAFFOLD.md` for the full service breakdown, connector contract, DDL notes, config format, dedupe strategy, and implementation plan. See `docs/ALOHA_SOURCE_FAMILY.md` for the Aloha-specific design notes.

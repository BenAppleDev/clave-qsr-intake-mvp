# QSR Intake MVP

A prototype data-intake and normalization layer for restaurant operations data.
It is built for internal tools, operator workflows, and grounded AI systems that need trustworthy POS, labor, and inventory inputs.
The local demo shows how raw source data can be preserved, normalized, and annotated with confidence and review metadata instead of being treated as clean by default.
This repo is intentionally honest about being an MVP: it demonstrates the architecture and workflow, not a production deployment.

## What Is Included

- Python connectors and workers for fast MVP iteration
- C++ runtime scaffold for long-running connector hosting
- PostgreSQL DDL for raw, staging, canonical, metadata, config, ops, and derived layers
- sample configs for API, CSV, inventory-report, and Aloha source patterns
- synthetic sample datasets for local demo use
- resolver configs for canonical item catalogs, aliases, overrides, and local embeddings

## Quick Start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the core demo:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo
```

Run the Aloha scenarios:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_a
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_b
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario all
```

Run the test suite:

```bash
pytest -q
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

## How The Demo Works

- source-shaped payloads and files are collected
- raw payloads are landed immutably
- staging records keep source shape while preparing for normalization
- canonical records are generated for orders, checks, line items, payments, shifts, and inventory events
- metadata captures provenance, freshness, quality, confidence, and review state

The core demo includes multi-store naming drift examples that produce:

- exact source-code alias matches
- high-confidence hybrid matches
- review-required ambiguous matches
- unresolved fallback matches

## Aloha Source Family

This MVP models Aloha as one source family with two operating modes:

- `integration_enabled`: a structured local integration surface exists and a collector polls that surface
- `local_bridge_fallback`: no practical integration surface exists, so a narrow local bridge uploads raw export or report files

Both modes land immutable raw payloads and feed the same downstream staging, normalization, canonical, metadata, and derived paths.

## Optional Local Infrastructure

If you want to test the PostgreSQL loading path or inspect a local object-store analogue:

```bash
docker compose up postgres minio
```

Then:

1. Apply SQL in `sql/migrations/`.
2. Export `DATABASE_URL`.
3. Run `PYTHONPATH=python python -m qsr_intake.pipeline.load_to_postgres`.

The Compose credentials are for local demo convenience only. Do not reuse them outside a disposable local environment.

## Documentation

- [`docs/DATA-FLOW.md`](/Users/ben/clave/qsr_intake_mvp/docs/DATA-FLOW.md)
- [`docs/USE-CASES.md`](/Users/ben/clave/qsr_intake_mvp/docs/USE-CASES.md)
- [`docs/HANDOFF.md`](/Users/ben/clave/qsr_intake_mvp/docs/HANDOFF.md)
- [`docs/IMPLEMENTATION_SCAFFOLD.md`](/Users/ben/clave/qsr_intake_mvp/docs/IMPLEMENTATION_SCAFFOLD.md)
- [`docs/ALOHA_SOURCE_FAMILY.md`](/Users/ben/clave/qsr_intake_mvp/docs/ALOHA_SOURCE_FAMILY.md)
- [`docs/NORMALIZATION_RESOLVER.md`](/Users/ben/clave/qsr_intake_mvp/docs/NORMALIZATION_RESOLVER.md)
- [`sample_data/README.md`](/Users/ben/clave/qsr_intake_mvp/sample_data/README.md)

## Notes On Scope

- sample data is synthetic and included only for local demonstration
- this repo favors transparency and inspectability over polish
- the current workflow is batch-first and file-oriented by design

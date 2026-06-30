# QSR Intake MVP

This repository contains a prototype intake and normalization system for restaurant operations data, with the main project living in `qsr_intake_mvp/`.
It is aimed at teams building internal tools, operator dashboards, workflow automation, or AI assistants that depend on messy POS, labor, and inventory inputs.
The demo proves that you can ingest heterogeneous source data, preserve raw truth, normalize it into canonical records, and attach review-friendly trust metadata.
The core claim is modest: before AI can be useful on operational systems, the underlying data needs provenance, replayability, confidence scoring, and clear handoff points for human review.

## What This Is

`qsr_intake_mvp/` is a batch-first scaffold for:

- raw landing of source payloads and files
- thin staging records
- canonical normalization across POS, labor, and inventory domains
- metadata for provenance, freshness, quality, and semantic confidence
- local demo scenarios for API-style sources and Aloha-style edge collection

This is a prototype and portfolio project, not a production-ready platform.

## Why I Built It

I wanted a concrete demo of a recurring applied-AI problem: organizations often want assistants, automation, and analytics before they have a trustworthy operational data layer. This repo focuses on the step before the assistant, where ingestion, normalization, and trust signals make downstream AI safer and more useful.

## What It Demonstrates

- design for messy operational systems rather than idealized APIs
- hybrid normalization with deterministic controls and human-review paths
- replayable raw ingestion with canonical outputs and record-level metadata
- support for uneven deployment environments, including local bridge collection

## How It Works

At a high level:

1. Source data is collected from sample API, CSV, report, or local-bridge inputs.
2. Raw payloads are stored immutably with ingestion metadata.
3. Staging records preserve source shape while preparing for normalization.
4. Workers map records into canonical business entities.
5. Metadata captures provenance, confidence, and review status.
6. Derived outputs can support dashboards, automation, and grounded AI workflows.

More detail lives in:

- [`qsr_intake_mvp/docs/DATA-FLOW.md`](/Users/ben/clave/qsr_intake_mvp/docs/DATA-FLOW.md)
- [`qsr_intake_mvp/docs/USE-CASES.md`](/Users/ben/clave/qsr_intake_mvp/docs/USE-CASES.md)
- [`qsr_intake_mvp/docs/HANDOFF.md`](/Users/ben/clave/qsr_intake_mvp/docs/HANDOFF.md)
- [`qsr_intake_mvp/docs/IMPLEMENTATION_SCAFFOLD.md`](/Users/ben/clave/qsr_intake_mvp/docs/IMPLEMENTATION_SCAFFOLD.md)

## Tech Stack

- Python workers and demo pipeline
- C++ runtime scaffold for long-running connector hosting
- PostgreSQL schema and migration files
- YAML configuration for connectors, mappings, and resolver behavior
- local file-based demo artifacts for inspection

## Repository Layout

The main project is nested under `qsr_intake_mvp/`:

```text
qsr_intake_mvp/
  cpp/
  docs/
  python/
  sample_data/
  sql/
  tests/
```

## How To Run Locally

From the repository root:

```bash
python -m pip install -r qsr_intake_mvp/requirements.txt
PYTHONPATH=qsr_intake_mvp/python python -m qsr_intake.pipeline.run_demo
```

Run the Aloha demo variants from the repository root:

```bash
PYTHONPATH=qsr_intake_mvp/python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_a
PYTHONPATH=qsr_intake_mvp/python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_b
PYTHONPATH=qsr_intake_mvp/python python -m qsr_intake.pipeline.run_demo --scenario all
```

From inside `qsr_intake_mvp/`:

```bash
cd qsr_intake_mvp
python -m pip install -r requirements.txt
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo
pytest -q
```

Optional local services for PostgreSQL and MinIO:

```bash
cd qsr_intake_mvp
docker compose up postgres minio
```

## Example Workflow

1. Run the demo to land raw sample data and generate canonical outputs.
2. Inspect `qsr_intake_mvp/demo_artifacts/` to see raw, staging, canonical, metadata, and derived files.
3. Review how ambiguous or drifted item names are either matched, flagged for review, or left unresolved with deterministic fallbacks.

## What I Would Improve Next

- a small UI for record review and override approval
- clearer schema docs and sample output snapshots
- more replay and drift-regression coverage
- packaged local setup for easier evaluator onboarding

## Relevance To Applied AI / Public-Interest Technology

This project is less about a model demo than about the data and workflow layer that makes applied AI accountable. It shows how to preserve source truth, surface confidence and review states, and support environments where systems are inconsistent, staff time is limited, and failures need to be recoverable rather than hidden.

## Project README

The implementation-focused README for the nested project is here:

- [`qsr_intake_mvp/README.md`](/Users/ben/clave/qsr_intake_mvp/README.md)

## License

No open-source license has been added yet. If you plan to publish the repository, MIT would be a reasonable default to consider, but it should be added intentionally.

# Handoff

## Setup Checklist

- Use Python 3.11 or newer.
- Create or activate a local virtual environment if desired.
- Install dependencies with `python -m pip install -r requirements.txt`.
- Work from `qsr_intake_mvp/` unless you are intentionally using the repo-root commands documented in the top-level README.

## Run Tests

```bash
pytest -q
```

## Run The Demo

Core scenario:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo
```

Aloha scenarios:

```bash
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_a
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario aloha_plan_b
PYTHONPATH=python python -m qsr_intake.pipeline.run_demo --scenario all
```

Optional PostgreSQL and MinIO:

```bash
docker compose up postgres minio
```

## Common Failure Points

- `ModuleNotFoundError: No module named 'qsr_intake'`
  - Usually means `PYTHONPATH=python` was not set when running from `qsr_intake_mvp/`, or the repo-root command did not use `PYTHONPATH=qsr_intake_mvp/python`.
- sentence-transformer model not present locally
  - The resolver config sets `local_files_only: true`. In an environment without the model cached locally, the code falls back to a deterministic embedding provider instead of failing the demo.
- stale demo artifacts causing confusion
  - Re-running the demo rewrites `demo_artifacts/`, so treat that directory as generated output.
- PostgreSQL loading path not working
  - Confirm `DATABASE_URL` is set and migrations in `sql/migrations/` have been applied.

## What A Future Maintainer Should Know

- This repo is a prototype. Favor clarity and replayability over premature abstraction.
- Raw landing is intentionally immutable; downstream fixes should happen in staging, normalization, configs, or review workflows.
- Resolver behavior is configuration-sensitive, so changes to aliases, thresholds, or catalogs can affect test expectations.
- The Aloha local bridge is deliberately narrow. It should collect and checkpoint files, not grow business-logic responsibilities.
- Sample data is synthetic and should stay synthetic if the repo is kept public.

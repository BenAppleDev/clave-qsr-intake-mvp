# MVP Implementation Scaffold

## 1. Service breakdown

### connector-runtime
- **Purpose:** host long-running connector processes, schedule collections, manage checkpoints, emit raw envelopes
- **Language:** C++
- **Why:** durable runtime shell, better fit for edge/on-prem deployment, steady host process
- **Notes:** can invoke Python connector adapters during the MVP if desired; should own heartbeat and checkpoint persistence

### raw-landing-writer
- **Purpose:** write immutable raw payloads/files to object storage and create `raw.ingestion_batches` / `raw.raw_objects`
- **Language:** Python for MVP, callable from runtime
- **Why:** faster to adapt for file, JSON, CSV, and report variants
- **Notes:** in a more mature system, object-store writing could be folded into the runtime

### staging-worker
- **Purpose:** parse source-shaped raw objects into thin staged records
- **Language:** Python
- **Why:** parser iteration and source variability dominate early effort

### normalization-worker
- **Purpose:** map staged records into canonical business entities
- **Language:** Python
- **Why:** rule iteration, config-driven transforms, trust scoring, and data-quality logic move faster here
- **Notes:** includes the hybrid token + embedding resolver for cross-store item and inventory naming drift

### metadata-trust annotator
- **Purpose:** attach provenance, freshness, quality, and semantic confidence data
- **Language:** Python
- **Why:** deterministic rule-based scoring is easier to evolve quickly

### config-loader
- **Purpose:** read immutable versioned configs for connectors, mapping rules, aliases, parser profiles, and crosswalks
- **Language:** Python
- **Why:** simple, low-friction, lives close to workers and demo tooling

### replay-job
- **Purpose:** re-run staging / normalization from prior raw objects without mutating source truth
- **Language:** Python
- **Why:** mostly orchestration and reprocessing logic

### metrics-health
- **Purpose:** runtime heartbeats, batch status counts, parse failures, stale source alerts
- **Language:** Python for MVP; runtime heartbeat in C++
- **Why:** startup pragmatism

## 2. Repository structure

```text
cpp/
  connector_runtime/
    include/
    src/
python/
  qsr_intake/
    connectors/
    staging/
    normalization/
    pipeline/
sample_data/
  raw/
  configs/
sql/
  migrations/
tests/
docs/
```

## 3. Shared connector contract

See:
- `cpp/connector_runtime/include/Connector.hpp`
- `python/qsr_intake/connectors/base.py`

Contract summary:
- `discover(window, config) -> handles`
- `collect(handle, config) -> RawEnvelope[]`
- `checkpoint(success_state) -> None`
- `heartbeat() -> HealthStatus`
- `describe_capabilities() -> dict`

## 4. Config schemas

The repo includes YAML examples for:
- connector config
- schedule config
- source auth
- source type parameters
- field mapping rules
- item alias rules
- canonical item catalog rules
- resolver thresholds, aliases, and store overrides
- store crosswalk rules
- parsing options

See `sample_data/configs/`.

## 5. PostgreSQL DDL

All SQL lives in `sql/migrations/`.

Implementation note:
- record-level trust metadata is consolidated into `meta.record_metadata`
- compatibility views for provenance/freshness/quality/confidence are created for teams that still want those logical splits
- `derived.daily_store_metrics` is derived, not canonical truth

## 6. Object storage strategy

Raw objects are stored under:

```text
raw/{customer_id}/{source_system}/{source_entity_type}/dt=YYYY-MM-DD/batch={batch_id}/obj={sequence}_{sha256}.{ext}
```

Replay writes new batch IDs and links back via `original_raw_object_id`.

## 7. Normalization pipeline

Core pipeline:
1. connectors emit `RawEnvelope`
2. raw landing persists immutable object + metadata
3. staging parser emits source-shaped records
4. normalizer resolves store/item/entity crosswalks, including hybrid token + embedding item resolution
5. canonical rows are upserted by natural key
6. metadata is attached by `record_uid`
7. derived metrics are computed from canonical outputs

## 8. Dedupe / idempotency

- raw object dedupe: `sha256`
- staged record dedupe: `record_fingerprint`
- canonical dedupe: natural keys + deterministic UUIDs
- replay safety: new batches can regenerate same canonical rows without duplication

## 9. Initial connector priorities

1. **Modern API orders connector**
   - fastest learning on order/check/item/payment normalization
2. **CSV labor connector**
   - representative of messy back-office exports
3. **Inventory report connector**
   - validates POS/labor/inventory convergence
4. **Aloha source family**
   - `integration_enabled` for structured local polling from Aloha integration surfaces
   - `local_bridge_fallback` for BOH file/report extraction with checkpointing and retries
5. **Generic local edge agent hardening**
   - only after the above contracts stabilize

## 10. Sample walkthrough

The demo covers:
- API orders payload
- CSV labor file
- inventory report extract

Run:

```bash
python -m qsr_intake.pipeline.run_demo
```

Then inspect:
- `demo_artifacts/raw/`
- `demo_artifacts/staging/`
- `demo_artifacts/canonical/`
- `demo_artifacts/meta/`
- `demo_artifacts/derived/`

## 11. Testing strategy

Tests included:
- parser correctness
- normalization correctness
- idempotency
- metadata presence
- resolver precedence and threshold behavior
- review-required and unresolved normalization paths

Future additions:
- config versioning validation
- stale data SLA tests
- replay regression tests
- schema drift tests

## 12. MVP plan

### Week 1-2
- schemas, configs, object-store layout, sample runtime scaffold

### Week 3-4
- API / CSV / inventory connectors
- raw landing
- staging parser

### Week 5-6
- canonical normalization
- record metadata
- end-to-end demo + PG load path

### Week 7+
- hardening, replay, checkpoints, drift handling, health signals

## Deviations from the earlier broad design

- `meta.ingestion_metadata` removed in favor of `raw.ingestion_batches`
- record-level trust metadata merged into `meta.record_metadata`
- `derived.daily_store_metrics` moved out of canonical truth
- `adjustments` retained only as an optional compatibility table
- Python owns most early connectors for speed; C++ owns the runtime/edge spine
- Aloha remains one source family, but source mode is explicit so local structured integration and local bridge fallback share the same central pipeline

# Aloha Source Family

## Why one family with two modes

Aloha is not modeled as one universal connector because the local operating reality varies by store:

- some stores expose a usable structured integration surface through locally configured Aloha interface components
- other stores only give you export files or reports from the BOH machine

Treating both as `source_family=aloha` keeps the connector taxonomy honest, while `source_mode` preserves how data was actually collected:

- `integration_enabled`
- `local_bridge_fallback`

The raw, staging, normalization, canonical, metadata, and derived layers stay shared.

## When to use each plan

Use Plan A when the store has a working local Aloha integration surface and it is realistic to poll or pull structured payloads.

Use Plan B when integration licensing, interface-terminal setup, BOH topology, or operational fragility make structured collection impractical. In that case a local bridge watches export/report files and uploads raw bytes deterministically.

## Why the local bridge is dumb

The bridge runs on fragile restaurant back-office hardware, so the implementation keeps responsibilities narrow:

- discover files
- read bytes
- annotate store/source metadata
- upload
- retry
- checkpoint
- emit simple health

It does not map canonical entities, interpret refunds or discounts, or make semantic decisions. That keeps recovery, replay, and pipeline consistency centered in the existing workers.

## Backfill vs live mode

Backfill is chunked and throttleable so older machines can walk historical files without hammering disk or network paths.

Live mode uses lightweight periodic scans and only uploads files not already checkpointed. Both modes feed the same raw landing contract, so a store can start with historical backfill and move into lighter ongoing sync without changing downstream processing.

## Effect on the connector model

This strengthens the Swiss-army-knife connector approach instead of replacing it:

- source families still represent the business system
- source modes capture how a family is reached in practice
- edge collection can vary per store
- the central raw-to-canonical pipeline remains stable

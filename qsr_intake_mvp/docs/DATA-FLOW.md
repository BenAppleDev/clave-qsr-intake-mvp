# Data Flow

## Overview

The demo follows a simple rule: source truth should be preserved before downstream logic starts interpreting it.

That leads to a pipeline with six stages:

1. source collection
2. raw landing
3. staging
4. normalization
5. metadata and trust annotation
6. output and review

## 1. Source Collection

The repo includes sample inputs for:

- API-style order payloads
- CSV labor exports
- inventory report extracts
- Aloha integration polling
- Aloha local bridge file pickup

Collectors are responsible for discovering and packaging source data, not for deciding business meaning.

## 2. Raw Landing

Collected payloads are written as immutable raw objects.

The raw layer exists so the system can:

- preserve original bytes
- support replay
- separate collection failures from interpretation failures
- maintain a clear audit trail

## 3. Staging

Staging records parse raw objects into source-shaped records without pretending the data is canonical.

This layer is useful for:

- parser iteration
- source-specific validation
- easier debugging when fields drift

## 4. Normalization

Normalization maps staged records into canonical entities such as:

- stores
- business days
- orders
- checks
- line items
- payments
- employees
- shift actuals
- inventory events

The item resolver uses a strict precedence chain:

1. exact source-code alias
2. store-specific override
3. exact cleaned-name alias
4. hybrid candidate scoring using token, character, and embedding signals
5. deterministic fallback with review state when confidence is not good enough

## 5. Metadata And Trust Fields

Trust metadata is stored alongside canonical output so downstream systems can reason about confidence instead of assuming perfect data.

Important fields include:

- provenance back to source records and raw objects
- freshness timing from source and ingestion windows
- semantic confidence scores
- normalization method
- human review requirements and status
- quality exceptions and resolver candidate details

This is the part that matters before AI becomes useful. If the system cannot explain where a fact came from, how confident it is, or whether a human should check it, an assistant built on top of it will be brittle.

## 6. Output And Review

The demo writes:

- raw artifacts
- staged records
- canonical records
- metadata records
- derived summaries

Review-required cases are intentionally preserved rather than silently “fixed.” That supports future workflows where a person approves overrides, resolves ambiguities, or investigates missing data.

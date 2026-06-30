# Normalization Resolver

## Purpose

The resolver lives in the central normalization worker and handles cross-store naming drift for:

- `line_item`
- `inventory_change`

It does not modify raw landing, staged payloads, or edge collectors.

## Resolution order

The resolver applies a strict precedence chain:

1. exact source-code alias
2. store-specific override
3. exact cleaned-name alias
4. hybrid candidate scoring using token features, char similarity, and local embeddings
5. review-required or unresolved source fallback

## Inputs

Resolver inputs are split across two configs:

- `sample_data/configs/canonical_item_catalog.yml`
- `sample_data/configs/normalization_resolver.yml`

The catalog defines customer-level canonical entries. The resolver config defines thresholds, weights, token cleanup rules, cleaned-name aliases, and store overrides.

## Output behavior

Matched rows write canonical `normalized_item_key` and `normalized_item_name`.

Review-required and unresolved rows keep deterministic source-derived fallback values in the canonical columns, while metadata records:

- match method
- confidence
- top candidates
- review-required state
- component scores

This keeps downstream outputs deterministic while preserving the audit trail for later override approval.

## Demo coverage

The core demo includes multi-store variations across the same customer umbrella:

- wildcard and misspelled burger naming resolved via hybrid matching
- ambiguous fries naming marked for review
- unknown drink and inventory names left unresolved
- store-specific inventory override for `Filter Oil`

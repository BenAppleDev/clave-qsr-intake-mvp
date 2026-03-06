CREATE OR REPLACE VIEW meta.provenance_metadata AS
SELECT
    record_uid,
    source_trace_id,
    raw_object_id,
    staged_record_id,
    source_system,
    source_family,
    source_entity_type,
    source_primary_key,
    source_location_id,
    mapping_rule_set_id,
    normalization_run_id
FROM meta.record_metadata;

CREATE OR REPLACE VIEW meta.freshness_metadata AS
SELECT
    record_uid,
    source_event_at,
    source_exported_at,
    extracted_at,
    normalized_at,
    expected_latency_seconds,
    freshness_seconds,
    freshness_status
FROM meta.record_metadata;

CREATE OR REPLACE VIEW meta.quality_metadata AS
SELECT
    record_uid,
    parse_status,
    quality_score,
    anomaly_flags
FROM meta.record_metadata;

CREATE OR REPLACE VIEW meta.semantic_confidence_metadata AS
SELECT
    record_uid,
    entity_confidence_score,
    normalization_exceptions,
    human_review_required,
    human_review_status,
    rule_version
FROM meta.record_metadata;

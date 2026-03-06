from __future__ import annotations

from typing import Any, Dict

from qsr_intake.utils import stable_hash


def build_record_metadata(
    *,
    record_uid: str,
    record_type: str,
    raw_object_id: str,
    staged_record_id: str,
    staged_record: Dict[str, Any],
    mapping_rule_set_id: str,
    normalization_run_id: str,
    quality_score: float,
    entity_confidence_score: float,
    anomaly_flags: dict | None = None,
    normalization_exceptions: dict | None = None,
) -> Dict[str, Any]:
    source_event_at = staged_record.get("source_event_at")
    extracted_at = staged_record.get("staged_at")
    freshness_seconds = 0
    freshness_status = "fresh" if source_event_at else "unknown"
    return {
        "record_uid": record_uid,
        "record_type": record_type,
        "raw_object_id": raw_object_id,
        "staged_record_id": staged_record_id,
        "source_trace_id": stable_hash([raw_object_id, staged_record_id, record_uid]),
        "source_system": staged_record["source_system"],
        "source_family": staged_record["source_family"],
        "source_entity_type": staged_record["source_entity_type"],
        "source_primary_key": staged_record.get("source_primary_key"),
        "source_location_id": staged_record.get("source_location_id"),
        "mapping_rule_set_id": mapping_rule_set_id,
        "normalization_run_id": normalization_run_id,
        "source_event_at": source_event_at,
        "source_exported_at": None,
        "extracted_at": extracted_at,
        "normalized_at": extracted_at,
        "expected_latency_seconds": 3600,
        "freshness_seconds": freshness_seconds,
        "freshness_status": freshness_status,
        "parse_status": staged_record.get("parse_status", "parseable"),
        "quality_score": quality_score,
        "entity_confidence_score": entity_confidence_score,
        "anomaly_flags": anomaly_flags or {},
        "normalization_exceptions": normalization_exceptions or {},
        "human_review_required": False,
        "human_review_status": "not_required",
        "rule_version": "v1",
    }

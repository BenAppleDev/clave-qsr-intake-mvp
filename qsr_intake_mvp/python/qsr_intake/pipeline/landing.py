from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List

from qsr_intake.connectors.base import RawEnvelope
from qsr_intake.staging.parser import parse_raw_object
from qsr_intake.storage import LocalObjectStore
from qsr_intake.utils import stable_hash, utc_now_iso


@dataclass
class LandingArtifacts:
    object_store: LocalObjectStore
    raw_batches: List[dict] = field(default_factory=list)
    raw_objects: List[dict] = field(default_factory=list)
    staged_records: List[dict] = field(default_factory=list)
    _sequence_by_batch: Dict[str, int] = field(default_factory=dict)

    def append_batch(
        self,
        *,
        config: Dict[str, Any],
        connector_name: str,
        connector_version: str,
        window: Dict[str, str | None] | None = None,
        status: str = "completed",
    ) -> dict:
        batch_id = config["batch_id"]
        schedule = config.get("schedule", {})
        window = window or {
            "window_start": schedule.get("window_start"),
            "window_end": schedule.get("window_end"),
        }
        row = {
            "batch_id": batch_id,
            "customer_id": config["customer_id"],
            "source_system": config["source_system"],
            "source_family": config["source_family"],
            "source_mode": config.get("source_mode", "standard"),
            "connector_name": connector_name,
            "connector_version": connector_version,
            "config_version": str(config["version"]),
            "window_start": window.get("window_start"),
            "window_end": window.get("window_end"),
            "extracted_at": utc_now_iso(),
            "received_at": utc_now_iso(),
            "status": status,
        }
        self.raw_batches.append(row)
        self._sequence_by_batch.setdefault(batch_id, 0)
        return row

    def land_envelope(self, config: Dict[str, Any], envelope: RawEnvelope) -> dict:
        sequence = self._next_sequence(envelope.batch_id)
        partition_date = _partition_date(config, envelope)
        extension = _extension_for(envelope.content_type)
        object_key = (
            f"raw/{config['customer_id']}/{config['source_system']}/{envelope.source_entity_type}/"
            f"dt={partition_date}/batch={envelope.batch_id}/obj={sequence}_{envelope.fingerprint}.{extension}"
        )
        self.object_store.put_bytes(object_key, envelope.payload_bytes)
        raw_object_id = stable_hash([envelope.batch_id, object_key])
        raw_row = {
            "raw_object_id": raw_object_id,
            "batch_id": envelope.batch_id,
            "customer_id": config["customer_id"],
            "source_system": config["source_system"],
            "source_family": envelope.source_family,
            "source_mode": envelope.source_mode,
            "source_entity_type": envelope.source_entity_type,
            "source_location_id": envelope.source_location_id,
            "source_object_id": envelope.source_object_id,
            "source_object_observed_at": envelope.source_object_observed_at,
            "object_key": object_key,
            "content_type": envelope.content_type,
            "byte_size": len(envelope.payload_bytes),
            "sha256": hashlib.sha256(envelope.payload_bytes).hexdigest(),
            "row_count_estimate": None,
            "received_at": utc_now_iso(),
            "inline_preview_jsonb": {
                "source_mode": envelope.source_mode,
                "source_object_id": envelope.source_object_id,
            },
            "is_replay": False,
            "original_raw_object_id": None,
        }
        self.raw_objects.append(raw_row)
        self.staged_records.extend(parse_raw_object(raw_row, envelope.payload_bytes))
        return raw_row

    def _next_sequence(self, batch_id: str) -> int:
        next_sequence = self._sequence_by_batch.get(batch_id, 0) + 1
        self._sequence_by_batch[batch_id] = next_sequence
        return next_sequence


def build_batch_id(config: Dict[str, Any], *parts: Any) -> str:
    schedule = config.get("schedule", {})
    return stable_hash(
        [
            config["customer_id"],
            config["source_system"],
            config["name"],
            schedule.get("window_start"),
            schedule.get("window_end"),
            *parts,
        ]
    )[:16]


def _partition_date(config: Dict[str, Any], envelope: RawEnvelope) -> str:
    if envelope.source_object_observed_at:
        return envelope.source_object_observed_at[:10]
    schedule = config.get("schedule", {})
    if schedule.get("window_start"):
        return schedule["window_start"][:10]
    return envelope.extracted_at[:10]


def _extension_for(content_type: str) -> str:
    if content_type == "application/json":
        return "json"
    if content_type == "text/csv":
        return "csv"
    return "bin"

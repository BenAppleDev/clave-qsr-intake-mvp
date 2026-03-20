from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from qsr_intake.connectors.base import BaseConnector, RawEnvelope
from qsr_intake.utils import stable_hash, utc_now_iso


class AlohaIntegrationConnector(BaseConnector):
    connector_name = "aloha_integration_connector"

    def discover(self, window: Dict[str, str], config: Dict[str, Any]) -> List[str]:
        sample_files = config.get("params", {}).get("sample_files")
        if sample_files:
            return [str(Path(path)) for path in sample_files]
        sample_file = config.get("sample_file")
        if sample_file:
            return [str(Path(sample_file))]
        raise ValueError("Aloha integration config requires params.sample_files or sample_file")

    def collect(self, handle: str, config: Dict[str, Any]) -> List[RawEnvelope]:
        payload = Path(handle).read_bytes()
        extracted_at = utc_now_iso()
        return [
            RawEnvelope(
                batch_id=config["batch_id"],
                customer_id=config["customer_id"],
                source_system=config["source_system"],
                source_family="aloha",
                source_mode=config.get("source_mode", "integration_enabled"),
                source_entity_type="aloha_integration_snapshot",
                source_location_id=config.get("source_location_id"),
                source_object_id=Path(handle).name,
                source_object_observed_at=None,
                extracted_at=extracted_at,
                content_type="application/json",
                connector_name=self.connector_name,
                connector_version=self.connector_version,
                config_version=str(config["version"]),
                fingerprint=stable_hash([config["customer_id"], config["source_system"], handle, len(payload)]),
                payload_bytes=payload,
            )
        ]

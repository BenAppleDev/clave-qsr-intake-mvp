from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RawEnvelope:
    batch_id: str
    customer_id: str
    source_system: str
    source_family: str
    source_entity_type: str
    source_location_id: Optional[str]
    source_object_id: Optional[str]
    source_object_observed_at: Optional[str]
    extracted_at: str
    content_type: str
    connector_name: str
    connector_version: str
    config_version: str
    fingerprint: str
    payload_bytes: bytes

    def to_metadata(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("payload_bytes")
        return data


class BaseConnector:
    connector_name: str = "base"
    connector_version: str = "0.1.0"

    def discover(self, window: Dict[str, str], config: Dict[str, Any]) -> List[str]:
        raise NotImplementedError

    def collect(self, handle: str, config: Dict[str, Any]) -> List[RawEnvelope]:
        raise NotImplementedError

    def checkpoint(self, success_state: str) -> None:
        return None

    def heartbeat(self) -> Dict[str, Any]:
        return {"ok": True, "connector_name": self.connector_name}

    def describe_capabilities(self) -> Dict[str, Any]:
        return {"connector_name": self.connector_name}

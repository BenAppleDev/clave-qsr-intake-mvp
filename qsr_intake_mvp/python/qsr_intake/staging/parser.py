from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any, Dict, List

from qsr_intake.utils import stable_hash, utc_now_iso


def parse_raw_object(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    source_entity_type = raw_object["source_entity_type"]
    if source_entity_type == "orders_page":
        return _parse_orders_page(raw_object, payload)
    if source_entity_type == "labor_csv":
        return _parse_csv_rows(raw_object, payload, "shift")
    if source_entity_type == "inventory_report":
        return _parse_csv_rows(raw_object, payload, "inventory_change")
    raise ValueError(f"Unsupported source entity type: {source_entity_type}")


def _base_staged(raw_object: Dict[str, Any], source_entity_type: str, source_primary_key: str | None, payload: Dict[str, Any], row_number: int | None = None) -> Dict[str, Any]:
    return {
        "staged_record_id": stable_hash([raw_object["raw_object_id"], source_entity_type, source_primary_key, row_number]),
        "batch_id": raw_object["batch_id"],
        "raw_object_id": raw_object["raw_object_id"],
        "customer_id": raw_object["customer_id"],
        "source_system": raw_object["source_system"],
        "source_family": raw_object["source_family"],
        "source_entity_type": source_entity_type,
        "source_location_id": payload.get("source_store_id") or raw_object.get("source_location_id"),
        "source_primary_key": source_primary_key,
        "row_number": row_number,
        "payload_path": None,
        "staged_payload": payload,
        "parse_status": "parseable",
        "parse_errors": {},
        "schema_version_detected": "v1",
        "source_event_at": payload.get("closedDate") or payload.get("clock_out") or payload.get("occurred_at") or payload.get("openedDate"),
        "staged_at": utc_now_iso(),
        "record_fingerprint": stable_hash([raw_object["source_system"], source_entity_type, source_primary_key, json.dumps(payload, sort_keys=True)]),
    }


def _parse_orders_page(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    doc = json.loads(payload.decode("utf-8"))
    records: List[Dict[str, Any]] = []
    store_id = doc["storeId"]
    for order in doc["orders"]:
        order_payload = {
            "source_store_id": store_id,
            "source_order_id": order["guid"],
            "state": order["state"],
            "channel": order["channel"],
            "openedDate": order["openedDate"],
            "closedDate": order["closedDate"],
            "totals": order["totals"],
        }
        records.append(_base_staged(raw_object, "order", order["guid"], order_payload))
        for check in order.get("checks", []):
            check_payload = {
                "source_store_id": store_id,
                "source_order_id": order["guid"],
                "source_check_id": check["guid"],
                "state": check["state"],
                "openedDate": check["openedDate"],
                "closedDate": check["closedDate"],
                "amount": check["amount"],
            }
            records.append(_base_staged(raw_object, "check", check["guid"], check_payload))
            for selection in check.get("selections", []):
                item_payload = {
                    "source_store_id": store_id,
                    "source_order_id": order["guid"],
                    "source_check_id": check["guid"],
                    "source_line_id": selection["guid"],
                    "source_item_code": selection["itemCode"],
                    "display_name": selection["displayName"],
                    "quantity": selection["quantity"],
                    "unit_price": selection["unitPrice"],
                    "tax": selection["tax"],
                    "voided_flag": selection.get("voided", False),
                    "comped_flag": selection.get("comped", False),
                    "menu_category": selection.get("menuCategory"),
                    "closedDate": order["closedDate"],
                }
                records.append(_base_staged(raw_object, "line_item", selection["guid"], item_payload))
            for payment in check.get("payments", []):
                payment_payload = {
                    "source_store_id": store_id,
                    "source_order_id": order["guid"],
                    "source_check_id": check["guid"],
                    "source_payment_id": payment["guid"],
                    "payment_type": payment["type"],
                    "amount": payment["amount"],
                    "tip_amount": payment.get("tipAmount", 0),
                    "captured_at": payment.get("capturedAt"),
                    "status": payment.get("status", "CAPTURED"),
                }
                records.append(_base_staged(raw_object, "payment", payment["guid"], payment_payload))
    return records


def _parse_csv_rows(raw_object: Dict[str, Any], payload: bytes, staged_type: str) -> List[Dict[str, Any]]:
    text = payload.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    records: List[Dict[str, Any]] = []
    key_field = "source_shift_id" if staged_type == "shift" else "source_inventory_event_id"
    for idx, row in enumerate(reader, start=2):
        cleaned = {k: v for k, v in row.items()}
        records.append(_base_staged(raw_object, staged_type, cleaned.get(key_field), cleaned, row_number=idx))
    return records

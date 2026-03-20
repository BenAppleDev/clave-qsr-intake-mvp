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
    if source_entity_type == "aloha_integration_snapshot":
        return _parse_aloha_integration_snapshot(raw_object, payload)
    if source_entity_type == "aloha_checks_export":
        return _parse_aloha_checks_export(raw_object, payload)
    if source_entity_type == "aloha_items_export":
        return _parse_aloha_items_export(raw_object, payload)
    if source_entity_type == "aloha_payments_export":
        return _parse_aloha_payments_export(raw_object, payload)
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
        "source_mode": raw_object.get("source_mode"),
        "source_entity_type": source_entity_type,
        "source_location_id": payload.get("source_store_id") or raw_object.get("source_location_id"),
        "source_primary_key": source_primary_key,
        "row_number": row_number,
        "payload_path": None,
        "staged_payload": payload,
        "parse_status": "parseable",
        "parse_errors": {},
        "schema_version_detected": "v1",
        "source_event_at": payload.get("closedDate") or payload.get("clock_out") or payload.get("occurred_at") or payload.get("captured_at") or payload.get("openedDate"),
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


def _parse_aloha_integration_snapshot(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    doc = json.loads(payload.decode("utf-8"))
    records: List[Dict[str, Any]] = []
    store_id = doc["store"]["storeId"]
    source_exported_at = doc["poll"]["pollEndedAt"]
    for check in doc["checks"]:
        order_payload = {
            "source_store_id": store_id,
            "source_order_id": check["orderRef"],
            "state": check["status"],
            "channel": check.get("channel", "IN_STORE"),
            "openedDate": check["openedAt"],
            "closedDate": check["closedAt"],
            "source_exported_at": source_exported_at,
            "totals": {
                "gross": check["totals"]["subtotal"],
                "net": check["totals"]["total"],
                "tax": check["totals"]["tax"],
                "discount": check["totals"].get("discount", 0.0),
                "tip": check["totals"].get("tip", 0.0),
                "refund": check["totals"].get("refund", 0.0),
                "void": check["totals"].get("void", 0.0),
            },
        }
        records.append(_base_staged(raw_object, "order", check["orderRef"], order_payload))

        check_payload = {
            "source_store_id": store_id,
            "source_order_id": check["orderRef"],
            "source_check_id": check["checkRef"],
            "state": check["status"],
            "openedDate": check["openedAt"],
            "closedDate": check["closedAt"],
            "source_exported_at": source_exported_at,
            "amount": {
                "subtotal": check["totals"]["subtotal"],
                "tax": check["totals"]["tax"],
                "total": check["totals"]["total"],
            },
        }
        records.append(_base_staged(raw_object, "check", check["checkRef"], check_payload))

        for item in check.get("items", []):
            item_payload = {
                "source_store_id": store_id,
                "source_order_id": check["orderRef"],
                "source_check_id": check["checkRef"],
                "source_line_id": item["lineRef"],
                "source_item_code": item["itemCode"],
                "display_name": item["displayName"],
                "quantity": item["quantity"],
                "unit_price": item["unitPrice"],
                "tax": item["tax"],
                "voided_flag": item.get("voided", False),
                "comped_flag": item.get("comped", False),
                "menu_category": item.get("menuCategory"),
                "closedDate": check["closedAt"],
                "source_exported_at": source_exported_at,
            }
            records.append(_base_staged(raw_object, "line_item", item["lineRef"], item_payload))

        for payment in check.get("payments", []):
            payment_payload = {
                "source_store_id": store_id,
                "source_order_id": check["orderRef"],
                "source_check_id": check["checkRef"],
                "source_payment_id": payment["paymentRef"],
                "payment_type": payment["type"],
                "amount": payment["amount"],
                "tip_amount": payment.get("tipAmount", 0.0),
                "captured_at": payment.get("capturedAt"),
                "status": payment.get("status", "CAPTURED"),
                "source_exported_at": source_exported_at,
            }
            records.append(_base_staged(raw_object, "payment", payment["paymentRef"], payment_payload))
    return records


def _parse_aloha_checks_export(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    reader = csv.DictReader(StringIO(payload.decode("utf-8")))
    records: List[Dict[str, Any]] = []
    for idx, row in enumerate(reader, start=2):
        order_payload = {
            "source_store_id": row["source_store_id"],
            "source_order_id": row["source_order_id"],
            "state": row["state"],
            "channel": row["channel"],
            "openedDate": row["openedDate"],
            "closedDate": row["closedDate"],
            "source_exported_at": row.get("source_exported_at"),
            "totals": {
                "gross": _to_float(row["subtotal"]),
                "net": _to_float(row["total"]),
                "tax": _to_float(row["tax"]),
                "discount": _to_float(row.get("discount", 0.0)),
                "tip": _to_float(row.get("tip", 0.0)),
                "refund": _to_float(row.get("refund", 0.0)),
                "void": _to_float(row.get("void", 0.0)),
            },
        }
        records.append(_base_staged(raw_object, "order", row["source_order_id"], order_payload, row_number=idx))

        check_payload = {
            "source_store_id": row["source_store_id"],
            "source_order_id": row["source_order_id"],
            "source_check_id": row["source_check_id"],
            "state": row["state"],
            "openedDate": row["openedDate"],
            "closedDate": row["closedDate"],
            "source_exported_at": row.get("source_exported_at"),
            "amount": {
                "subtotal": _to_float(row["subtotal"]),
                "tax": _to_float(row["tax"]),
                "total": _to_float(row["total"]),
            },
        }
        records.append(_base_staged(raw_object, "check", row["source_check_id"], check_payload, row_number=idx))
    return records


def _parse_aloha_items_export(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    reader = csv.DictReader(StringIO(payload.decode("utf-8")))
    records: List[Dict[str, Any]] = []
    for idx, row in enumerate(reader, start=2):
        item_payload = {
            "source_store_id": row["source_store_id"],
            "source_order_id": row["source_order_id"],
            "source_check_id": row["source_check_id"],
            "source_line_id": row["source_line_id"],
            "source_item_code": row["source_item_code"],
            "display_name": row["display_name"],
            "quantity": _to_float(row["quantity"]),
            "unit_price": _to_float(row["unit_price"]),
            "tax": _to_float(row["tax"]),
            "voided_flag": _to_bool(row.get("voided_flag")),
            "comped_flag": _to_bool(row.get("comped_flag")),
            "menu_category": row.get("menu_category"),
            "closedDate": row["closedDate"],
            "source_exported_at": row.get("source_exported_at"),
        }
        records.append(_base_staged(raw_object, "line_item", row["source_line_id"], item_payload, row_number=idx))
    return records


def _parse_aloha_payments_export(raw_object: Dict[str, Any], payload: bytes) -> List[Dict[str, Any]]:
    reader = csv.DictReader(StringIO(payload.decode("utf-8")))
    records: List[Dict[str, Any]] = []
    for idx, row in enumerate(reader, start=2):
        payment_payload = {
            "source_store_id": row["source_store_id"],
            "source_order_id": row["source_order_id"],
            "source_check_id": row["source_check_id"],
            "source_payment_id": row["source_payment_id"],
            "payment_type": row["payment_type"],
            "amount": _to_float(row["amount"]),
            "tip_amount": _to_float(row.get("tip_amount", 0.0)),
            "captured_at": row.get("captured_at"),
            "status": row.get("status", "CAPTURED"),
            "source_exported_at": row.get("source_exported_at"),
        }
        records.append(_base_staged(raw_object, "payment", row["source_payment_id"], payment_payload, row_number=idx))
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


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}

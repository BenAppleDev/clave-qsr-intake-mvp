from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from qsr_intake.normalization.metadata import build_record_metadata
from qsr_intake.normalization.resolver import CatalogResolver, ResolutionResult
from qsr_intake.utils import deterministic_uuid, stable_hash, utc_now_iso


@dataclass
class NormalizationContext:
    customer_id: str
    store_crosswalk: Dict[str, Dict[str, Any]]
    item_aliases: Dict[str, Dict[str, Any]]
    item_resolver: CatalogResolver | None = None
    mapping_rule_set_id: str = "default_qsr_rules_v1"


class Normalizer:
    def __init__(self, context: NormalizationContext) -> None:
        self.context = context
        self.normalization_run_id = deterministic_uuid("normalization_run", context.customer_id, utc_now_iso())

        self.outputs: Dict[str, List[Dict[str, Any]]] = {
            "stores": [],
            "business_days": [],
            "orders": [],
            "checks": [],
            "line_items": [],
            "payments": [],
            "employees": [],
            "shift_actuals": [],
            "inventory_events": [],
            "record_metadata": [],
            "daily_store_metrics": [],
        }

        self._stores_seen: set[str] = set()
        self._business_days_seen: set[Tuple[str, str]] = set()
        self._orders_seen: set[str] = set()
        self._checks_seen: set[str] = set()
        self._line_items_seen: set[str] = set()
        self._payments_seen: set[str] = set()
        self._employees_seen: set[str] = set()
        self._shifts_seen: set[str] = set()
        self._inventory_seen: set[str] = set()

    def normalize(self, staged_records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        for record in staged_records:
            if record["parse_status"] != "parseable":
                continue
            entity_type = record["source_entity_type"]
            if entity_type == "order":
                self._normalize_order(record)
            elif entity_type == "check":
                self._normalize_check(record)
            elif entity_type == "line_item":
                self._normalize_line_item(record)
            elif entity_type == "payment":
                self._normalize_payment(record)
            elif entity_type == "shift":
                self._normalize_shift(record)
            elif entity_type == "inventory_change":
                self._normalize_inventory(record)

        self._derive_daily_metrics()
        return self.outputs

    def _resolve_store(self, source_store_id: str | None) -> Dict[str, Any]:
        if source_store_id is None or source_store_id not in self.context.store_crosswalk:
            raise KeyError(f"Unknown source store ID: {source_store_id}")
        store = self.context.store_crosswalk[source_store_id]
        store_id = store["store_id"]
        if store_id not in self._stores_seen:
            row = {
                "store_id": store_id,
                "record_uid": deterministic_uuid("store", self.context.customer_id, store_id),
                "customer_id": self.context.customer_id,
                "store_code": store["store_code"],
                "store_name": store["store_name"],
                "brand_name": store["brand_name"],
                "timezone": store["timezone"],
                "currency": store.get("currency", "USD"),
                "status": "active",
                "business_day_cutoff_local_time": store.get("business_day_cutoff_local_time", "04:00:00"),
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
            self.outputs["stores"].append(row)
            self._stores_seen.add(store_id)
        return store

    def _resolve_business_day(self, store: Dict[str, Any], timestamp: str | None) -> Dict[str, Any]:
        if timestamp is None:
            business_date = "unknown"
        else:
            business_date = timestamp[:10]
        key = (store["store_id"], business_date)
        if key not in self._business_days_seen:
            row = {
                "business_day_id": deterministic_uuid("business_day", *key),
                "record_uid": deterministic_uuid("business_day_record", *key),
                "customer_id": self.context.customer_id,
                "store_id": store["store_id"],
                "business_date": business_date,
                "opened_at": None,
                "closed_at": None,
                "source_day_key": None,
                "is_closed_out": False,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
            self.outputs["business_days"].append(row)
            self._business_days_seen.add(key)
            return row
        for row in self.outputs["business_days"]:
            if row["store_id"] == store["store_id"] and row["business_date"] == business_date:
                return row
        raise RuntimeError("Business day lookup failed")

    def _append_metadata(
        self,
        record_uid: str,
        record_type: str,
        staged_record: Dict[str, Any],
        quality_score: float = 1.0,
        entity_confidence_score: float = 1.0,
        anomaly_flags: dict | None = None,
        normalization_exceptions: dict | None = None,
        human_review_required: bool = False,
        human_review_status: str = "not_required",
    ) -> None:
        metadata = build_record_metadata(
            record_uid=record_uid,
            record_type=record_type,
            raw_object_id=staged_record["raw_object_id"],
            staged_record_id=staged_record["staged_record_id"],
            staged_record=staged_record,
            mapping_rule_set_id=self.context.mapping_rule_set_id,
            normalization_run_id=self.normalization_run_id,
            quality_score=quality_score,
            entity_confidence_score=entity_confidence_score,
            anomaly_flags=anomaly_flags,
            normalization_exceptions=normalization_exceptions,
            human_review_required=human_review_required,
            human_review_status=human_review_status,
        )
        self.outputs["record_metadata"].append(metadata)

    def _normalize_order(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        business_day = self._resolve_business_day(store, payload.get("closedDate"))
        order_id = deterministic_uuid(self.context.customer_id, staged["source_system"], payload["source_order_id"], store["store_id"])
        if order_id in self._orders_seen:
            return
        row = {
            "order_id": order_id,
            "record_uid": deterministic_uuid("order_record", order_id),
            "customer_id": self.context.customer_id,
            "store_id": store["store_id"],
            "business_day_id": business_day["business_day_id"],
            "source_system": staged["source_system"],
            "source_order_id": payload["source_order_id"],
            "channel": payload["channel"],
            "status": payload["state"].lower(),
            "opened_at": payload["openedDate"],
            "closed_at": payload["closedDate"],
            "gross_amount": payload["totals"]["gross"],
            "net_amount": payload["totals"]["net"],
            "tax_amount": payload["totals"]["tax"],
            "discount_amount": payload["totals"]["discount"],
            "tip_amount": payload["totals"]["tip"],
            "refund_amount": payload["totals"]["refund"],
            "void_amount": payload["totals"]["void"],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["orders"].append(row)
        self._orders_seen.add(order_id)
        self._append_metadata(row["record_uid"], "order", staged)

    def _normalize_check(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        order_id = deterministic_uuid(self.context.customer_id, staged["source_system"], payload["source_order_id"], store["store_id"])
        check_id = deterministic_uuid("check", order_id, payload["source_check_id"])
        if check_id in self._checks_seen:
            return
        row = {
            "check_id": check_id,
            "record_uid": deterministic_uuid("check_record", check_id),
            "customer_id": self.context.customer_id,
            "order_id": order_id,
            "source_check_id": payload["source_check_id"],
            "status": payload["state"].lower(),
            "opened_at": payload["openedDate"],
            "closed_at": payload["closedDate"],
            "subtotal_amount": payload["amount"]["subtotal"],
            "tax_amount": payload["amount"]["tax"],
            "total_amount": payload["amount"]["total"],
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["checks"].append(row)
        self._checks_seen.add(check_id)
        self._append_metadata(row["record_uid"], "check", staged)

    def _normalize_line_item(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        order_id = deterministic_uuid(self.context.customer_id, staged["source_system"], payload["source_order_id"], store["store_id"])
        check_id = deterministic_uuid("check", order_id, payload["source_check_id"])
        line_id = deterministic_uuid("line_item", check_id, payload["source_line_id"])
        if line_id in self._line_items_seen:
            return
        resolution = self._resolve_catalog_item(
            domain="line_item",
            store_id=payload["source_store_id"],
            source_item_code=payload.get("source_item_code"),
            source_name=payload.get("display_name"),
            menu_category=payload.get("menu_category"),
            unit_price=float(payload["unit_price"]),
        )
        row = {
            "line_item_id": line_id,
            "record_uid": deterministic_uuid("line_item_record", line_id),
            "customer_id": self.context.customer_id,
            "order_id": order_id,
            "check_id": check_id,
            "source_line_id": payload["source_line_id"],
            "source_item_code": payload["source_item_code"],
            "display_name": payload["display_name"],
            "normalized_item_name": resolution.normalized_item_name,
            "normalized_item_key": resolution.normalized_item_key,
            "quantity": float(payload["quantity"]),
            "unit_price": float(payload["unit_price"]),
            "extended_price": round(float(payload["quantity"]) * float(payload["unit_price"]), 2),
            "discount_amount": 0.0,
            "tax_amount": float(payload["tax"]),
            "voided_flag": bool(payload["voided_flag"]),
            "comped_flag": bool(payload["comped_flag"]),
            "menu_category": payload.get("menu_category"),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["line_items"].append(row)
        self._line_items_seen.add(line_id)
        self._append_metadata(
            row["record_uid"],
            "line_item",
            staged,
            entity_confidence_score=resolution.confidence,
            normalization_exceptions={"resolver": resolution.debug_metadata},
            human_review_required=resolution.human_review_required,
            human_review_status=resolution.human_review_status,
        )

    def _normalize_payment(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        order_id = deterministic_uuid(self.context.customer_id, staged["source_system"], payload["source_order_id"], store["store_id"])
        check_id = deterministic_uuid("check", order_id, payload["source_check_id"])
        payment_id = deterministic_uuid("payment", check_id, payload["source_payment_id"])
        if payment_id in self._payments_seen:
            return
        row = {
            "payment_id": payment_id,
            "record_uid": deterministic_uuid("payment_record", payment_id),
            "customer_id": self.context.customer_id,
            "order_id": order_id,
            "check_id": check_id,
            "source_payment_id": payload["source_payment_id"],
            "payment_type": payload["payment_type"].lower(),
            "status": payload["status"].lower(),
            "amount": float(payload["amount"]),
            "tip_amount": float(payload["tip_amount"]),
            "authorized_at": None,
            "captured_at": payload.get("captured_at"),
            "voided_flag": False,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["payments"].append(row)
        self._payments_seen.add(payment_id)
        self._append_metadata(row["record_uid"], "payment", staged)

    def _normalize_shift(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        business_day = self._resolve_business_day(store, payload.get("clock_out") or payload.get("clock_in"))
        employee_id = deterministic_uuid(self.context.customer_id, staged["source_system"], payload["source_employee_id"], store["store_id"])
        if employee_id not in self._employees_seen:
            employee_row = {
                "employee_id": employee_id,
                "record_uid": deterministic_uuid("employee_record", employee_id),
                "customer_id": self.context.customer_id,
                "store_id": store["store_id"],
                "source_employee_id": payload["source_employee_id"],
                "display_name": payload["display_name"],
                "employment_status": "active",
                "role_name": payload["role_name"],
                "hire_date": None,
                "active_flag": True,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
            self.outputs["employees"].append(employee_row)
            self._employees_seen.add(employee_id)
            self._append_metadata(employee_row["record_uid"], "employee", staged)
        shift_id = deterministic_uuid("shift_actual", employee_id, payload["source_shift_id"])
        if shift_id in self._shifts_seen:
            return
        clock_in = payload["clock_in"]
        clock_out = payload["clock_out"]
        labor_cost = round(_duration_hours(clock_in, clock_out) * float(payload["hourly_wage"]), 2)
        row = {
            "shift_actual_id": shift_id,
            "record_uid": deterministic_uuid("shift_record", shift_id),
            "customer_id": self.context.customer_id,
            "employee_id": employee_id,
            "store_id": store["store_id"],
            "business_day_id": business_day["business_day_id"],
            "source_shift_id": payload["source_shift_id"],
            "role_name": payload["role_name"],
            "clock_in": clock_in,
            "clock_out": clock_out,
            "break_minutes_paid": int(payload.get("break_minutes_paid", 0)),
            "break_minutes_unpaid": int(payload.get("break_minutes_unpaid", 0)),
            "declared_cash_tips": float(payload.get("declared_cash_tips", 0)),
            "hourly_wage": float(payload["hourly_wage"]),
            "labor_cost": labor_cost,
            "status": payload["status"].lower(),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["shift_actuals"].append(row)
        self._shifts_seen.add(shift_id)
        self._append_metadata(row["record_uid"], "shift_actual", staged)

    def _normalize_inventory(self, staged: Dict[str, Any]) -> None:
        payload = staged["staged_payload"]
        store = self._resolve_store(payload["source_store_id"])
        business_day = self._resolve_business_day(store, payload.get("occurred_at"))
        inv_id = deterministic_uuid("inventory_event", store["store_id"], payload["source_inventory_event_id"])
        if inv_id in self._inventory_seen:
            return
        resolution = self._resolve_catalog_item(
            domain="inventory",
            store_id=payload["source_store_id"],
            source_item_code=payload.get("source_item_code"),
            source_name=payload.get("source_item_name"),
            unit_of_measure=payload.get("unit_of_measure"),
        )
        row = {
            "inventory_event_id": inv_id,
            "record_uid": deterministic_uuid("inventory_record", inv_id),
            "customer_id": self.context.customer_id,
            "store_id": store["store_id"],
            "business_day_id": business_day["business_day_id"],
            "source_inventory_event_id": payload["source_inventory_event_id"],
            "source_item_code": payload["source_item_code"],
            "normalized_item_name": resolution.normalized_item_name,
            "normalized_item_key": resolution.normalized_item_key,
            "event_type": payload["event_type"],
            "quantity_delta": float(payload["quantity_delta"]),
            "unit_of_measure": payload["unit_of_measure"],
            "unit_cost": float(payload["unit_cost"]),
            "occurred_at": payload["occurred_at"],
            "reference_document_id": payload.get("reference_document_id"),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        self.outputs["inventory_events"].append(row)
        self._inventory_seen.add(inv_id)
        self._append_metadata(
            row["record_uid"],
            "inventory_event",
            staged,
            entity_confidence_score=resolution.confidence,
            normalization_exceptions={"resolver": resolution.debug_metadata},
            human_review_required=resolution.human_review_required,
            human_review_status=resolution.human_review_status,
        )

    def _resolve_catalog_item(
        self,
        *,
        domain: str,
        store_id: str,
        source_item_code: str | None,
        source_name: str | None,
        menu_category: str | None = None,
        unit_price: float | None = None,
        unit_of_measure: str | None = None,
    ) -> ResolutionResult:
        if self.context.item_resolver is not None:
            return self.context.item_resolver.resolve(
                domain=domain,
                source_store_id=store_id,
                source_item_code=source_item_code,
                source_name=source_name,
                menu_category=menu_category,
                unit_price=unit_price,
                unit_of_measure=unit_of_measure,
            )
        fallback_name = source_name or source_item_code or "Unknown Item"
        fallback_key = stable_hash([domain, store_id, source_item_code, fallback_name])[:16]
        alias = self.context.item_aliases.get(source_item_code or "", {
            "normalized_item_key": fallback_key,
            "normalized_item_name": fallback_name,
            "confidence": 0.75,
        })
        return ResolutionResult(
            normalized_item_key=str(alias["normalized_item_key"]),
            normalized_item_name=str(alias["normalized_item_name"]),
            confidence=float(alias.get("confidence", 0.75)),
            status="matched",
            method="source_code_alias",
            human_review_required=False,
            human_review_status="not_required",
            debug_metadata={
                "status": "matched",
                "method": "source_code_alias",
                "source_cleaned_name": fallback_name.lower(),
                "domain": domain,
                "chosen_key": str(alias["normalized_item_key"]),
                "top_candidates": [],
                "token_similarity": 1.0,
                "vector_similarity": 1.0,
                "char_similarity": 1.0,
                "category_bonus": 0.0,
                "price_or_uom_bonus": 0.0,
                "store_override_applied": False,
                "catalog_version": "not_loaded",
                "resolver_version": "legacy",
            },
        )

    def _derive_daily_metrics(self) -> None:
        orders_by_bd = defaultdict(list)
        for order in self.outputs["orders"]:
            orders_by_bd[(order["store_id"], order["business_day_id"])].append(order)

        shifts_by_bd = defaultdict(list)
        for shift in self.outputs["shift_actuals"]:
            shifts_by_bd[(shift["store_id"], shift["business_day_id"])].append(shift)

        inventory_by_bd = defaultdict(list)
        for event in self.outputs["inventory_events"]:
            inventory_by_bd[(event["store_id"], event["business_day_id"])].append(event)

        keys = set(orders_by_bd) | set(shifts_by_bd) | set(inventory_by_bd)
        for store_id, business_day_id in sorted(keys):
            orders = orders_by_bd.get((store_id, business_day_id), [])
            shifts = shifts_by_bd.get((store_id, business_day_id), [])
            events = inventory_by_bd.get((store_id, business_day_id), [])
            gross_sales = round(sum(float(o["gross_amount"]) for o in orders), 2)
            net_sales = round(sum(float(o["net_amount"]) for o in orders), 2)
            transaction_count = len(orders)
            avg_ticket = round(net_sales / transaction_count, 2) if transaction_count else 0.0
            labor_hours = round(sum(_duration_hours(s["clock_in"], s["clock_out"]) for s in shifts), 2)
            labor_cost = round(sum(float(s["labor_cost"]) for s in shifts), 2)
            inventory_received_cost = round(sum(abs(float(e["quantity_delta"])) * float(e["unit_cost"]) for e in events if e["event_type"] == "receive"), 2)
            inventory_waste_cost = round(sum(abs(float(e["quantity_delta"])) * float(e["unit_cost"]) for e in events if e["event_type"] == "waste"), 2)
            row = {
                "daily_store_metrics_id": deterministic_uuid("daily_metrics", store_id, business_day_id),
                "record_uid": deterministic_uuid("daily_metrics_record", store_id, business_day_id),
                "customer_id": self.context.customer_id,
                "store_id": store_id,
                "business_day_id": business_day_id,
                "gross_sales": gross_sales,
                "net_sales": net_sales,
                "transaction_count": transaction_count,
                "average_ticket": avg_ticket,
                "labor_hours": labor_hours,
                "labor_cost": labor_cost,
                "inventory_received_cost": inventory_received_cost,
                "inventory_waste_cost": inventory_waste_cost,
                "data_completeness_score": 1.0,
                "derived_at": utc_now_iso(),
                "derived_from_run_id": self.normalization_run_id,
                "input_window_start": None,
                "input_window_end": None,
            }
            self.outputs["daily_store_metrics"].append(row)


def _duration_hours(clock_in: str, clock_out: str) -> float:
    start = datetime.fromisoformat(clock_in)
    end = datetime.fromisoformat(clock_out)
    return max((end - start).total_seconds() / 3600.0, 0.0)

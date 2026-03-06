-- raw layer
CREATE TABLE IF NOT EXISTS raw.ingestion_batches (
    batch_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_family TEXT NOT NULL,
    connector_name TEXT NOT NULL,
    connector_version TEXT NOT NULL,
    config_version TEXT NOT NULL,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    extracted_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.raw_objects (
    raw_object_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES raw.ingestion_batches(batch_id),
    customer_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_family TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_location_id TEXT,
    source_object_id TEXT,
    source_object_observed_at TIMESTAMPTZ,
    object_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    row_count_estimate INTEGER,
    received_at TIMESTAMPTZ NOT NULL,
    inline_preview_jsonb JSONB DEFAULT '{}'::jsonb,
    is_replay BOOLEAN NOT NULL DEFAULT FALSE,
    original_raw_object_id TEXT REFERENCES raw.raw_objects(raw_object_id)
);

-- staging layer
CREATE TABLE IF NOT EXISTS staging.staged_records (
    staged_record_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES raw.ingestion_batches(batch_id),
    raw_object_id TEXT NOT NULL REFERENCES raw.raw_objects(raw_object_id),
    customer_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_family TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_location_id TEXT,
    source_primary_key TEXT,
    row_number INTEGER,
    payload_path TEXT,
    staged_payload JSONB NOT NULL,
    parse_status TEXT NOT NULL,
    parse_errors JSONB DEFAULT '{}'::jsonb,
    schema_version_detected TEXT,
    source_event_at TIMESTAMPTZ,
    staged_at TIMESTAMPTZ NOT NULL,
    record_fingerprint TEXT NOT NULL
);

-- canonical truth layer
CREATE TABLE IF NOT EXISTS canonical.stores (
    store_id TEXT PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_code TEXT NOT NULL,
    store_name TEXT NOT NULL,
    brand_name TEXT,
    timezone TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL,
    business_day_cutoff_local_time TIME NOT NULL DEFAULT '04:00:00',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical.business_days (
    business_day_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES canonical.stores(store_id),
    business_date DATE NOT NULL,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    source_day_key TEXT,
    is_closed_out BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (store_id, business_date)
);

CREATE TABLE IF NOT EXISTS canonical.orders (
    order_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES canonical.stores(store_id),
    business_day_id UUID NOT NULL REFERENCES canonical.business_days(business_day_id),
    source_system TEXT NOT NULL,
    source_order_id TEXT NOT NULL,
    channel TEXT,
    status TEXT NOT NULL,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    gross_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    tip_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    refund_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    void_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (customer_id, source_system, source_order_id, store_id)
);

CREATE TABLE IF NOT EXISTS canonical.checks (
    check_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    order_id UUID NOT NULL REFERENCES canonical.orders(order_id),
    source_check_id TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    subtotal_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (order_id, source_check_id)
);

CREATE TABLE IF NOT EXISTS canonical.line_items (
    line_item_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    order_id UUID NOT NULL REFERENCES canonical.orders(order_id),
    check_id UUID REFERENCES canonical.checks(check_id),
    source_line_id TEXT NOT NULL,
    source_item_code TEXT,
    display_name TEXT NOT NULL,
    normalized_item_name TEXT,
    normalized_item_key TEXT,
    quantity NUMERIC(12,4) NOT NULL DEFAULT 0,
    unit_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    extended_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    voided_flag BOOLEAN NOT NULL DEFAULT FALSE,
    comped_flag BOOLEAN NOT NULL DEFAULT FALSE,
    menu_category TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (check_id, source_line_id)
);

CREATE TABLE IF NOT EXISTS canonical.payments (
    payment_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    order_id UUID NOT NULL REFERENCES canonical.orders(order_id),
    check_id UUID REFERENCES canonical.checks(check_id),
    source_payment_id TEXT NOT NULL,
    payment_type TEXT NOT NULL,
    status TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    tip_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    authorized_at TIMESTAMPTZ,
    captured_at TIMESTAMPTZ,
    voided_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (order_id, source_payment_id)
);

-- optional compatibility table; can remain unused in v1
CREATE TABLE IF NOT EXISTS canonical.adjustments (
    adjustment_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_record_uid UUID NOT NULL,
    adjustment_kind TEXT NOT NULL,
    source_reason_code TEXT,
    reason_text TEXT,
    amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical.employees (
    employee_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_id TEXT REFERENCES canonical.stores(store_id),
    source_employee_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    employment_status TEXT,
    role_name TEXT,
    hire_date DATE,
    active_flag BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (customer_id, source_employee_id, store_id)
);

CREATE TABLE IF NOT EXISTS canonical.shift_actuals (
    shift_actual_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    employee_id UUID NOT NULL REFERENCES canonical.employees(employee_id),
    store_id TEXT NOT NULL REFERENCES canonical.stores(store_id),
    business_day_id UUID NOT NULL REFERENCES canonical.business_days(business_day_id),
    source_shift_id TEXT NOT NULL,
    role_name TEXT,
    clock_in TIMESTAMPTZ NOT NULL,
    clock_out TIMESTAMPTZ,
    break_minutes_paid INTEGER NOT NULL DEFAULT 0,
    break_minutes_unpaid INTEGER NOT NULL DEFAULT 0,
    declared_cash_tips NUMERIC(12,2) NOT NULL DEFAULT 0,
    hourly_wage NUMERIC(12,2),
    labor_cost NUMERIC(12,2),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (customer_id, source_shift_id)
);

CREATE TABLE IF NOT EXISTS canonical.inventory_events (
    inventory_event_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES canonical.stores(store_id),
    business_day_id UUID REFERENCES canonical.business_days(business_day_id),
    source_inventory_event_id TEXT NOT NULL,
    source_item_code TEXT,
    normalized_item_name TEXT,
    normalized_item_key TEXT,
    event_type TEXT NOT NULL,
    quantity_delta NUMERIC(12,4) NOT NULL,
    unit_of_measure TEXT,
    unit_cost NUMERIC(12,4),
    occurred_at TIMESTAMPTZ NOT NULL,
    reference_document_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (customer_id, source_inventory_event_id)
);

-- consolidated record-level trust metadata
CREATE TABLE IF NOT EXISTS meta.record_metadata (
    record_uid UUID PRIMARY KEY,
    record_type TEXT NOT NULL,
    raw_object_id TEXT NOT NULL REFERENCES raw.raw_objects(raw_object_id),
    staged_record_id TEXT NOT NULL REFERENCES staging.staged_records(staged_record_id),
    source_trace_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_family TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_primary_key TEXT,
    source_location_id TEXT,
    mapping_rule_set_id TEXT NOT NULL,
    normalization_run_id UUID NOT NULL,
    source_event_at TIMESTAMPTZ,
    source_exported_at TIMESTAMPTZ,
    extracted_at TIMESTAMPTZ,
    normalized_at TIMESTAMPTZ NOT NULL,
    expected_latency_seconds INTEGER,
    freshness_seconds INTEGER,
    freshness_status TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    quality_score NUMERIC(6,4) NOT NULL,
    entity_confidence_score NUMERIC(6,4) NOT NULL,
    anomaly_flags JSONB DEFAULT '{}'::jsonb,
    normalization_exceptions JSONB DEFAULT '{}'::jsonb,
    human_review_required BOOLEAN NOT NULL DEFAULT FALSE,
    human_review_status TEXT NOT NULL DEFAULT 'not_required',
    rule_version TEXT NOT NULL
);

-- config / ops / derived
CREATE TABLE IF NOT EXISTS config.connector_configs (
    connector_config_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_family TEXT NOT NULL,
    config_version TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    config_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config.mapping_rule_sets (
    mapping_rule_set_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    canonical_target_type TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    rules_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS config.external_id_crosswalks (
    crosswalk_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    external_id_type TEXT NOT NULL,
    external_id_value TEXT NOT NULL,
    confidence NUMERIC(6,4) NOT NULL DEFAULT 1.0,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS config.item_aliases (
    item_alias_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_item_code TEXT NOT NULL,
    normalized_item_key TEXT NOT NULL,
    normalized_item_name TEXT NOT NULL,
    confidence NUMERIC(6,4) NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS config.parser_profiles (
    parser_profile_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_entity_type TEXT NOT NULL,
    profile_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ops.normalization_runs (
    normalization_run_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    notes JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.connector_checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    customer_id TEXT NOT NULL,
    connector_name TEXT NOT NULL,
    source_system TEXT NOT NULL,
    checkpoint_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS derived.daily_store_metrics (
    daily_store_metrics_id UUID PRIMARY KEY,
    record_uid UUID NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    store_id TEXT NOT NULL REFERENCES canonical.stores(store_id),
    business_day_id UUID NOT NULL REFERENCES canonical.business_days(business_day_id),
    gross_sales NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_sales NUMERIC(12,2) NOT NULL DEFAULT 0,
    transaction_count INTEGER NOT NULL DEFAULT 0,
    average_ticket NUMERIC(12,2) NOT NULL DEFAULT 0,
    labor_hours NUMERIC(12,2) NOT NULL DEFAULT 0,
    labor_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    inventory_received_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    inventory_waste_cost NUMERIC(12,2) NOT NULL DEFAULT 0,
    data_completeness_score NUMERIC(6,4) NOT NULL DEFAULT 1.0,
    derived_at TIMESTAMPTZ NOT NULL,
    derived_from_run_id UUID NOT NULL REFERENCES ops.normalization_runs(normalization_run_id),
    input_window_start TIMESTAMPTZ,
    input_window_end TIMESTAMPTZ
);

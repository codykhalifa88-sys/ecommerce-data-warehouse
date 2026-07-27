-- ============================================================================
-- staging schema: raw, mostly-TEXT tables mirroring the Olist source CSVs 1:1
-- No constraints beyond primary staging keys — real typing/cleaning happens
-- in etl/clean.py and the sql/transforms load scripts, not here.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS etl_control;

-- olist_customers_dataset.csv
CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id               TEXT,
    customer_unique_id        TEXT,
    customer_zip_code_prefix  TEXT,
    customer_city             TEXT,
    customer_state            TEXT,
    _loaded_at                TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_geolocation_dataset.csv
CREATE TABLE IF NOT EXISTS staging.geolocation (
    geolocation_zip_code_prefix TEXT,
    geolocation_lat             TEXT,
    geolocation_lng             TEXT,
    geolocation_city            TEXT,
    geolocation_state           TEXT,
    _loaded_at                  TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_order_items_dataset.csv
CREATE TABLE IF NOT EXISTS staging.order_items (
    order_id             TEXT,
    order_item_id        TEXT,
    product_id           TEXT,
    seller_id            TEXT,
    shipping_limit_date  TEXT,
    price                TEXT,
    freight_value        TEXT,
    _loaded_at           TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_order_payments_dataset.csv
CREATE TABLE IF NOT EXISTS staging.order_payments (
    order_id             TEXT,
    payment_sequential   TEXT,
    payment_type         TEXT,
    payment_installments TEXT,
    payment_value        TEXT,
    _loaded_at           TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_order_reviews_dataset.csv
CREATE TABLE IF NOT EXISTS staging.order_reviews (
    review_id                TEXT,
    order_id                 TEXT,
    review_score              TEXT,
    review_comment_title      TEXT,
    review_comment_message    TEXT,
    review_creation_date      TEXT,
    review_answer_timestamp   TEXT,
    _loaded_at                TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_orders_dataset.csv
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id                       TEXT,
    customer_id                    TEXT,
    order_status                   TEXT,
    order_purchase_timestamp       TEXT,
    order_approved_at              TEXT,
    order_delivered_carrier_date   TEXT,
    order_delivered_customer_date  TEXT,
    order_estimated_delivery_date  TEXT,
    _loaded_at                     TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_products_dataset.csv
CREATE TABLE IF NOT EXISTS staging.products (
    product_id                  TEXT,
    product_category_name       TEXT,
    product_name_lenght         TEXT,
    product_description_lenght  TEXT,
    product_photos_qty          TEXT,
    product_weight_g            TEXT,
    product_length_cm           TEXT,
    product_height_cm           TEXT,
    product_width_cm            TEXT,
    category_name_en            TEXT, -- populated by etl/clean.py from the translation file
    _loaded_at                  TIMESTAMP NOT NULL DEFAULT now()
);

-- olist_sellers_dataset.csv
CREATE TABLE IF NOT EXISTS staging.sellers (
    seller_id                 TEXT,
    seller_zip_code_prefix    TEXT,
    seller_city               TEXT,
    seller_state              TEXT,
    _loaded_at                TIMESTAMP NOT NULL DEFAULT now()
);

-- product_category_name_translation.csv
CREATE TABLE IF NOT EXISTS staging.product_category_name_translation (
    product_category_name          TEXT,
    product_category_name_english  TEXT,
    _loaded_at                     TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================================
-- etl_control: watermarks + pipeline observability (incremental loading,
-- idempotency, and lineage support — see section 13 of the project brief)
-- ============================================================================

CREATE TABLE IF NOT EXISTS etl_control.load_log (
    id               SERIAL PRIMARY KEY,
    table_name       TEXT NOT NULL,
    last_loaded_at   TIMESTAMP NOT NULL,
    rows_loaded      INT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('success', 'failed')),
    run_started_at   TIMESTAMP NOT NULL DEFAULT now(),
    run_finished_at  TIMESTAMP,
    error_message    TEXT
);

CREATE TABLE IF NOT EXISTS etl_control.pipeline_metadata (
    id            SERIAL PRIMARY KEY,
    source_table  TEXT NOT NULL,
    target_table  TEXT NOT NULL,
    rows_in       INT,
    rows_out      INT,
    stage         TEXT NOT NULL, -- extract | clean | load
    run_at        TIMESTAMP NOT NULL DEFAULT now()
);

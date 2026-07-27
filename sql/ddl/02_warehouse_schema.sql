-- ============================================================================
-- warehouse schema: star schema for e-commerce analytics
-- Unique constraints on natural keys exist specifically so load scripts can
-- use INSERT ... ON CONFLICT DO UPDATE (idempotent re-runs, no duplicates).
-- ============================================================================

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key     INT PRIMARY KEY,       -- YYYYMMDD
    full_date    DATE NOT NULL UNIQUE,
    day          INT NOT NULL,
    month        INT NOT NULL,
    month_name   TEXT NOT NULL,
    quarter      INT NOT NULL,
    year         INT NOT NULL,
    day_of_week  TEXT NOT NULL,
    is_weekend   BOOLEAN NOT NULL
);

-- SCD Type 2: a new row is inserted whenever customer_city/state changes,
-- so historical orders keep pointing at the location as-of purchase time.
CREATE TABLE IF NOT EXISTS warehouse.dim_customer (
    customer_key         SERIAL PRIMARY KEY,
    customer_id          TEXT NOT NULL,      -- natural key from source
    customer_city        TEXT,
    customer_state       TEXT,
    customer_zip_prefix  TEXT,
    valid_from            DATE NOT NULL,
    valid_to               DATE,              -- NULL = current record
    is_current              BOOLEAN NOT NULL DEFAULT TRUE
);

-- Only one current row per natural key at a time. Partial unique index
-- (rather than a table-wide UNIQUE) because is_current=false rows are
-- expected to repeat customer_id across history.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_customer_current
    ON warehouse.dim_customer (customer_id)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS warehouse.dim_product (
    product_key       SERIAL PRIMARY KEY,
    product_id        TEXT NOT NULL UNIQUE,
    category_name     TEXT,
    category_name_en  TEXT,
    weight_g          NUMERIC,
    length_cm         NUMERIC,
    height_cm         NUMERIC,
    width_cm          NUMERIC
);

CREATE TABLE IF NOT EXISTS warehouse.dim_seller (
    seller_key    SERIAL PRIMARY KEY,
    seller_id     TEXT NOT NULL UNIQUE,
    seller_city   TEXT,
    seller_state  TEXT
);

CREATE TABLE IF NOT EXISTS warehouse.dim_geography (
    geo_key          SERIAL PRIMARY KEY,
    zip_code_prefix  TEXT NOT NULL UNIQUE,
    city             TEXT,
    state            TEXT,
    lat              NUMERIC,
    lng              NUMERIC
);

CREATE TABLE IF NOT EXISTS warehouse.fact_orders (
    order_key          SERIAL PRIMARY KEY,
    order_id           TEXT NOT NULL,
    order_item_id      TEXT NOT NULL DEFAULT '1',
    customer_key       INT REFERENCES warehouse.dim_customer(customer_key),
    product_key        INT REFERENCES warehouse.dim_product(product_key),
    seller_key         INT REFERENCES warehouse.dim_seller(seller_key),
    order_date_key     INT REFERENCES warehouse.dim_date(date_key),
    delivery_date_key  INT REFERENCES warehouse.dim_date(date_key),
    order_status       TEXT,
    price              NUMERIC,
    freight_value      NUMERIC,
    payment_value      NUMERIC,
    payment_type       TEXT,
    installments       INT,
    review_score       INT,
    delivery_days      INT,          -- computed: delivery_date - order_date
    is_late            BOOLEAN,      -- computed: delivered after estimate
    UNIQUE (order_id, order_item_id)
);

CREATE INDEX IF NOT EXISTS ix_fact_orders_order_date   ON warehouse.fact_orders (order_date_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_customer_key  ON warehouse.fact_orders (customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_product_key    ON warehouse.fact_orders (product_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_seller_key      ON warehouse.fact_orders (seller_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_order_id         ON warehouse.fact_orders (order_id);

-- NOTE: at ~100K orders this table doesn't need partitioning yet, but in a
-- production-scale version fact_orders would be range-partitioned by
-- order_date_key (monthly) to keep index maintenance and vacuum costs down
-- as the table grows past tens of millions of rows.

# Data Dictionary

All tables live in the `warehouse` schema unless noted. Types are as declared
in `sql/ddl/02_warehouse_schema.sql`.

## warehouse.dim_date

| Column | Type | Source | Business meaning |
|---|---|---|---|
| date_key | INT (PK) | generated | Surrogate key, `YYYYMMDD` |
| full_date | DATE | generated | Calendar date |
| day / month / year | INT | derived | Calendar parts of `full_date` |
| month_name | TEXT | derived | e.g. "January" |
| quarter | INT | derived | 1-4 |
| day_of_week | TEXT | derived | e.g. "Monday" |
| is_weekend | BOOLEAN | derived | True for Sat/Sun |

## warehouse.dim_customer (SCD Type 2)

| Column | Type | Source | Business meaning |
|---|---|---|---|
| customer_key | SERIAL (PK) | generated | Surrogate key |
| customer_id | TEXT | `olist_customers_dataset.customer_id` | Natural key; repeats across history rows |
| customer_city / customer_state | TEXT | `olist_customers_dataset` | Location as of `valid_from` |
| customer_zip_prefix | TEXT | `olist_customers_dataset.customer_zip_code_prefix` | First digits of postal code |
| valid_from / valid_to | DATE | ETL-assigned | History window; `valid_to IS NULL` = current |
| is_current | BOOLEAN | ETL-assigned | True for exactly one row per `customer_id` |

Why SCD Type 2: customer city/state can change over time, and historical
orders should reflect the location at time of purchase for accurate regional
analysis — see README "Key Design Decisions".

## warehouse.dim_product

| Column | Type | Source | Business meaning |
|---|---|---|---|
| product_key | SERIAL (PK) | generated | Surrogate key |
| product_id | TEXT | `olist_products_dataset.product_id` | Natural key |
| category_name | TEXT | `olist_products_dataset.product_category_name` | Original (Portuguese) category |
| category_name_en | TEXT | `product_category_name_translation` | English category, falls back to original if untranslated |
| weight_g / length_cm / height_cm / width_cm | NUMERIC | `olist_products_dataset` | Package dimensions, median-imputed when missing |

## warehouse.dim_seller

| Column | Type | Source | Business meaning |
|---|---|---|---|
| seller_key | SERIAL (PK) | generated | Surrogate key |
| seller_id | TEXT | `olist_sellers_dataset.seller_id` | Natural key |
| seller_city / seller_state | TEXT | `olist_sellers_dataset` | Seller location |

## warehouse.dim_geography

| Column | Type | Source | Business meaning |
|---|---|---|---|
| geo_key | SERIAL (PK) | generated | Surrogate key |
| zip_code_prefix | TEXT | `olist_geolocation_dataset` | Natural key, one row per prefix |
| city / state | TEXT | `olist_geolocation_dataset` | Modal city/state for that prefix |
| lat / lng | NUMERIC | `olist_geolocation_dataset` | Mean coordinates for that prefix |

## warehouse.fact_orders

Grain: one row per order line item (`order_id` + `order_item_id`).

| Column | Type | Source | Business meaning |
|---|---|---|---|
| order_key | SERIAL (PK) | generated | Surrogate key |
| order_id | TEXT | `olist_orders_dataset.order_id` | Natural order identifier |
| order_item_id | TEXT | `olist_order_items_dataset.order_item_id` | Line item number within the order |
| customer_key | INT (FK) | joined via `dim_customer` (current row) | Who bought |
| product_key | INT (FK) | joined via `dim_product` | What was bought |
| seller_key | INT (FK) | joined via `dim_seller` | Who sold it |
| order_date_key | INT (FK) | `order_purchase_timestamp` | When the order was placed |
| delivery_date_key | INT (FK), nullable | `order_delivered_customer_date` | When it arrived; null if undelivered |
| order_status | TEXT | `olist_orders_dataset.order_status` | e.g. delivered, shipped, canceled |
| price | NUMERIC | `olist_order_items_dataset.price` | Item price |
| freight_value | NUMERIC | `olist_order_items_dataset.freight_value` | Shipping cost for this item |
| payment_value | NUMERIC | `olist_order_payments_dataset` | Total paid for the order (summed across payment rows) |
| payment_type | TEXT | `olist_order_payments_dataset` | Method used on the first payment sequence |
| installments | INT | `olist_order_payments_dataset` | Installment count on the first payment sequence |
| review_score | INT, nullable | `olist_order_reviews_dataset.review_score` | 1-5 customer rating |
| delivery_days | INT, nullable | computed | `delivery_date - order_date` |
| is_late | BOOLEAN, nullable | computed | `delivered_date > estimated_delivery_date` |

## staging schema

Mirrors each source CSV 1:1 with all-TEXT columns plus `_loaded_at`. See
`sql/ddl/01_staging_schema.sql`. Not typed or deduplicated — that happens in
`etl/clean.py` before the warehouse load.

## etl_control schema

| Table | Purpose |
|---|---|
| `load_log` | Per-table watermark, row count, and status for each extract run (incremental loading) |
| `pipeline_metadata` | Source → target row counts per load stage, for lineage/observability |

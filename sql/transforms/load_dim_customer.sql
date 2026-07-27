-- SCD Type 2: preserve customer location history so historical orders keep
-- pointing at the city/state that was current at time of purchase.
--
-- Idempotency: rerunning this on the same day is safe. After the first run,
-- every staging customer whose city/state matches its current dim row no
-- longer qualifies as "changed", so step 1 expires nothing and step 2 finds
-- an existing current match for every staging row, so it inserts nothing.

-- Step 1: expire current rows whose city/state has changed in the source.
WITH changed AS (
    SELECT dc.customer_key
    FROM warehouse.dim_customer dc
    JOIN staging.customers sc ON sc.customer_id = dc.customer_id
    WHERE dc.is_current
      AND (
          dc.customer_city IS DISTINCT FROM sc.customer_city
          OR dc.customer_state IS DISTINCT FROM sc.customer_state
      )
)
UPDATE warehouse.dim_customer
SET valid_to = CURRENT_DATE, is_current = FALSE
WHERE customer_key IN (SELECT customer_key FROM changed);

-- Step 2: insert brand-new customers, and new current versions of customers
-- that were just expired above.
INSERT INTO warehouse.dim_customer (
    customer_id, customer_city, customer_state, customer_zip_prefix,
    valid_from, valid_to, is_current
)
SELECT
    sc.customer_id, sc.customer_city, sc.customer_state, sc.customer_zip_code_prefix,
    CURRENT_DATE, NULL, TRUE
FROM staging.customers sc
LEFT JOIN warehouse.dim_customer dc
    ON dc.customer_id = sc.customer_id AND dc.is_current
WHERE dc.customer_key IS NULL;

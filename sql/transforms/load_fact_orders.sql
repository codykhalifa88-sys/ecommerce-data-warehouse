-- Grain: one row per order line item. Payments are aggregated to order level
-- (sum of all payment rows = total paid; type/installments taken from the
-- first payment sequence) since fact_orders carries one payment_type per row.
-- ON CONFLICT (order_id, order_item_id) makes reruns idempotent — no
-- duplicate line items, and any late-arriving review/payment data updates
-- the existing row instead of inserting a second one.
WITH payments_agg AS (
    SELECT
        order_id,
        SUM(NULLIF(payment_value, '')::NUMERIC) AS payment_value,
        MAX(payment_type) FILTER (WHERE NULLIF(payment_sequential, '')::INT = 1) AS payment_type,
        MAX(NULLIF(payment_installments, '')::INT) FILTER (WHERE NULLIF(payment_sequential, '')::INT = 1) AS installments
    FROM staging.order_payments
    GROUP BY order_id
),
reviews AS (
    SELECT order_id, NULLIF(review_score, '')::INT AS review_score
    FROM staging.order_reviews
)
INSERT INTO warehouse.fact_orders (
    order_id, order_item_id, customer_key, product_key, seller_key,
    order_date_key, delivery_date_key, order_status, price, freight_value,
    payment_value, payment_type, installments, review_score,
    delivery_days, is_late
)
SELECT
    o.order_id,
    oi.order_item_id,
    dc.customer_key,
    dp.product_key,
    ds.seller_key,
    TO_CHAR(o.order_purchase_timestamp::TIMESTAMP, 'YYYYMMDD')::INT AS order_date_key,
    CASE WHEN o.order_delivered_customer_date IS NOT NULL
         THEN TO_CHAR(o.order_delivered_customer_date::TIMESTAMP, 'YYYYMMDD')::INT END AS delivery_date_key,
    o.order_status,
    NULLIF(oi.price, '')::NUMERIC AS price,
    NULLIF(oi.freight_value, '')::NUMERIC AS freight_value,
    pay.payment_value,
    pay.payment_type,
    pay.installments,
    rev.review_score,
    CASE WHEN o.order_delivered_customer_date IS NOT NULL
         THEN (o.order_delivered_customer_date::TIMESTAMP::DATE - o.order_purchase_timestamp::TIMESTAMP::DATE)
         END AS delivery_days,
    CASE WHEN o.order_delivered_customer_date IS NOT NULL AND o.order_estimated_delivery_date IS NOT NULL
         THEN o.order_delivered_customer_date::TIMESTAMP::DATE > o.order_estimated_delivery_date::TIMESTAMP::DATE
         END AS is_late
FROM staging.orders o
JOIN staging.order_items oi ON oi.order_id = o.order_id
LEFT JOIN warehouse.dim_customer dc ON dc.customer_id = o.customer_id AND dc.is_current
LEFT JOIN warehouse.dim_product dp ON dp.product_id = oi.product_id
LEFT JOIN warehouse.dim_seller ds ON ds.seller_id = oi.seller_id
LEFT JOIN payments_agg pay ON pay.order_id = o.order_id
LEFT JOIN reviews rev ON rev.order_id = o.order_id
ON CONFLICT (order_id, order_item_id) DO UPDATE SET
    customer_key = EXCLUDED.customer_key,
    product_key = EXCLUDED.product_key,
    seller_key = EXCLUDED.seller_key,
    order_date_key = EXCLUDED.order_date_key,
    delivery_date_key = EXCLUDED.delivery_date_key,
    order_status = EXCLUDED.order_status,
    price = EXCLUDED.price,
    freight_value = EXCLUDED.freight_value,
    payment_value = EXCLUDED.payment_value,
    payment_type = EXCLUDED.payment_type,
    installments = EXCLUDED.installments,
    review_score = EXCLUDED.review_score,
    delivery_days = EXCLUDED.delivery_days,
    is_late = EXCLUDED.is_late;

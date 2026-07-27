-- ============================================================================
-- Business analysis queries against warehouse.fact_orders / dim_*
-- Run against a loaded warehouse: psql -f analysis/business_questions.sql
-- ============================================================================

-- 1. Monthly revenue trend
SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.price + f.freight_value)::NUMERIC, 2) AS revenue
FROM warehouse.fact_orders f
JOIN warehouse.dim_date d ON d.date_key = f.order_date_key
WHERE f.order_status NOT IN ('canceled', 'unavailable')
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;


-- 2. Top 10 product categories by revenue
SELECT
    COALESCE(p.category_name_en, 'unknown') AS category,
    ROUND(SUM(f.price + f.freight_value)::NUMERIC, 2) AS revenue,
    COUNT(*) AS line_items
FROM warehouse.fact_orders f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
WHERE f.order_status NOT IN ('canceled', 'unavailable')
GROUP BY category
ORDER BY revenue DESC
LIMIT 10;


-- 3. Average delivery time by state, and % of late deliveries by state
SELECT
    c.customer_state,
    ROUND(AVG(f.delivery_days)::NUMERIC, 1) AS avg_delivery_days,
    ROUND(
        100.0 * SUM(CASE WHEN f.is_late THEN 1 ELSE 0 END) / NULLIF(COUNT(*) FILTER (WHERE f.is_late IS NOT NULL), 0),
        1
    ) AS pct_late_deliveries,
    COUNT(*) AS delivered_orders
FROM warehouse.fact_orders f
JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
WHERE f.delivery_days IS NOT NULL
GROUP BY c.customer_state
ORDER BY pct_late_deliveries DESC;


-- 4. Customer cohort retention: first purchase month -> repeat purchase rate by month offset
WITH first_purchase AS (
    SELECT
        c.customer_id,
        MIN(DATE_TRUNC('month', d.full_date)) AS cohort_month
    FROM warehouse.fact_orders f
    JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
    JOIN warehouse.dim_date d ON d.date_key = f.order_date_key
    GROUP BY c.customer_id
),
orders_with_cohort AS (
    SELECT
        c.customer_id,
        fp.cohort_month,
        DATE_TRUNC('month', d.full_date) AS order_month
    FROM warehouse.fact_orders f
    JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
    JOIN warehouse.dim_date d ON d.date_key = f.order_date_key
    JOIN first_purchase fp ON fp.customer_id = c.customer_id
),
cohort_activity AS (
    SELECT
        cohort_month,
        order_month,
        (DATE_PART('year', order_month) - DATE_PART('year', cohort_month)) * 12
            + (DATE_PART('month', order_month) - DATE_PART('month', cohort_month)) AS month_offset,
        COUNT(DISTINCT customer_id) AS active_customers
    FROM orders_with_cohort
    GROUP BY cohort_month, order_month
),
cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_customers
    FROM first_purchase
    GROUP BY cohort_month
)
SELECT
    ca.cohort_month,
    ca.month_offset,
    ca.active_customers,
    cs.cohort_customers,
    ROUND(100.0 * ca.active_customers / cs.cohort_customers, 1) AS retention_pct
FROM cohort_activity ca
JOIN cohort_size cs ON cs.cohort_month = ca.cohort_month
ORDER BY ca.cohort_month, ca.month_offset;


-- 5. Payment type distribution and average installments by category
SELECT
    COALESCE(p.category_name_en, 'unknown') AS category,
    f.payment_type,
    COUNT(*) AS orders,
    ROUND(AVG(f.installments)::NUMERIC, 1) AS avg_installments
FROM warehouse.fact_orders f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
WHERE f.payment_type IS NOT NULL
GROUP BY category, f.payment_type
ORDER BY category, orders DESC;


-- 6. Review score correlation with delivery delay: late vs on-time orders
SELECT
    CASE WHEN f.is_late THEN 'late' ELSE 'on_time' END AS delivery_outcome,
    ROUND(AVG(f.review_score)::NUMERIC, 2) AS avg_review_score,
    COUNT(*) AS orders
FROM warehouse.fact_orders f
WHERE f.is_late IS NOT NULL AND f.review_score IS NOT NULL
GROUP BY delivery_outcome
ORDER BY delivery_outcome;

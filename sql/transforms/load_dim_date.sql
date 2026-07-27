-- Calendar dimension spanning the Olist dataset's order + estimated-delivery
-- range with headroom on both sides. ON CONFLICT DO NOTHING keeps reruns
-- idempotent — the calendar never changes once generated.
INSERT INTO warehouse.dim_date (
    date_key, full_date, day, month, month_name, quarter, year, day_of_week, is_weekend
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT AS date_key,
    d::DATE AS full_date,
    EXTRACT(DAY FROM d)::INT AS day,
    EXTRACT(MONTH FROM d)::INT AS month,
    TRIM(TO_CHAR(d, 'Month')) AS month_name,
    EXTRACT(QUARTER FROM d)::INT AS quarter,
    EXTRACT(YEAR FROM d)::INT AS year,
    TRIM(TO_CHAR(d, 'Day')) AS day_of_week,
    EXTRACT(ISODOW FROM d) IN (6, 7) AS is_weekend
FROM generate_series('2016-01-01'::DATE, '2020-12-31'::DATE, INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

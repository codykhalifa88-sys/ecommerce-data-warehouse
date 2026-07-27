INSERT INTO warehouse.dim_product (
    product_id, category_name, category_name_en, weight_g, length_cm, height_cm, width_cm
)
SELECT
    product_id,
    product_category_name,
    category_name_en,
    NULLIF(product_weight_g, '')::NUMERIC,
    NULLIF(product_length_cm, '')::NUMERIC,
    NULLIF(product_height_cm, '')::NUMERIC,
    NULLIF(product_width_cm, '')::NUMERIC
FROM staging.products
ON CONFLICT (product_id) DO UPDATE SET
    category_name = EXCLUDED.category_name,
    category_name_en = EXCLUDED.category_name_en,
    weight_g = EXCLUDED.weight_g,
    length_cm = EXCLUDED.length_cm,
    height_cm = EXCLUDED.height_cm,
    width_cm = EXCLUDED.width_cm;

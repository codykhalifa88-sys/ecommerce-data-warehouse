INSERT INTO warehouse.dim_seller (seller_id, seller_city, seller_state)
SELECT seller_id, seller_city, seller_state
FROM staging.sellers
ON CONFLICT (seller_id) DO UPDATE SET
    seller_city = EXCLUDED.seller_city,
    seller_state = EXCLUDED.seller_state;

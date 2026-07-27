-- One row per zip prefix. Multiple raw geolocation pings per prefix get
-- collapsed to the modal city/state and mean lat/lng.
INSERT INTO warehouse.dim_geography (zip_code_prefix, city, state, lat, lng)
SELECT
    geolocation_zip_code_prefix AS zip_code_prefix,
    MODE() WITHIN GROUP (ORDER BY geolocation_city) AS city,
    MODE() WITHIN GROUP (ORDER BY geolocation_state) AS state,
    AVG(NULLIF(geolocation_lat, '')::NUMERIC) AS lat,
    AVG(NULLIF(geolocation_lng, '')::NUMERIC) AS lng
FROM staging.geolocation
WHERE geolocation_zip_code_prefix IS NOT NULL
GROUP BY geolocation_zip_code_prefix
ON CONFLICT (zip_code_prefix) DO UPDATE SET
    city = EXCLUDED.city,
    state = EXCLUDED.state,
    lat = EXCLUDED.lat,
    lng = EXCLUDED.lng;

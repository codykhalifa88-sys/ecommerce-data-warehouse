"""
Unit tests for the pure-pandas cleaning logic in etl/clean.py. These don't
touch Postgres, so they run fast and are safe in CI without a database.
"""
import pandas as pd

from etl.clean import (
    clean_customers,
    clean_order_items,
    clean_order_payments,
    clean_orders,
    clean_products,
)


def test_clean_customers_deduplicates_and_fills_nulls():
    df = pd.DataFrame(
        {
            "customer_id": ["a", "a", "b"],
            "customer_unique_id": ["u1", "u1", "u2"],
            "customer_zip_code_prefix": ["01001", "01001", "02002"],
            "customer_city": [" Sao Paulo ", " Sao Paulo ", None],
            "customer_state": ["sp", "sp", None],
        }
    )
    cleaned, report = clean_customers(df)

    assert len(cleaned) == 2
    assert report.duplicates_removed == 1
    assert cleaned.loc[cleaned["customer_id"] == "a", "customer_city"].iloc[0] == "sao paulo"
    assert cleaned.loc[cleaned["customer_id"] == "b", "customer_state"].iloc[0] == "UNKNOWN"


def test_clean_products_translates_category_and_imputes_dimensions():
    products = pd.DataFrame(
        {
            "product_id": ["p1", "p2"],
            "product_category_name": ["beleza_saude", None],
            "product_weight_g": ["500", None],
            "product_length_cm": ["10", "20"],
            "product_height_cm": ["5", "5"],
            "product_width_cm": ["8", "8"],
        }
    )
    translation = pd.DataFrame(
        {
            "product_category_name": ["beleza_saude"],
            "product_category_name_english": ["health_beauty"],
        }
    )
    cleaned, report = clean_products(products, translation)

    assert cleaned.loc[cleaned["product_id"] == "p1", "category_name_en"].iloc[0] == "health_beauty"
    # p2 has no category at all -> falls back to 'unknown' and stays 'unknown' post-merge
    assert cleaned.loc[cleaned["product_id"] == "p2", "category_name_en"].iloc[0] == "unknown"
    assert not cleaned["product_weight_g"].isna().any()


def test_clean_orders_drops_rows_without_purchase_timestamp():
    df = pd.DataFrame(
        {
            "order_id": ["o1", "o2"],
            "customer_id": ["c1", "c2"],
            "order_status": ["Delivered", "Shipped"],
            "order_purchase_timestamp": ["2018-01-01 10:00:00", None],
            "order_approved_at": ["2018-01-01 11:00:00", None],
            "order_delivered_carrier_date": [None, None],
            "order_delivered_customer_date": [None, None],
            "order_estimated_delivery_date": ["2018-01-10 00:00:00", None],
        }
    )
    cleaned, report = clean_orders(df)

    assert len(cleaned) == 1
    assert cleaned.iloc[0]["order_status"] == "delivered"
    assert any("dropped 1" in note for note in report.notes)


def test_clean_order_items_drops_unparseable_prices():
    df = pd.DataFrame(
        {
            "order_id": ["o1", "o1", "o2"],
            "order_item_id": ["1", "1", "1"],
            "product_id": ["p1", "p1", "p2"],
            "seller_id": ["s1", "s1", "s2"],
            "shipping_limit_date": ["x", "x", "y"],
            "price": ["19.90", "19.90", "not_a_number"],
            "freight_value": ["5.0", "5.0", None],
        }
    )
    cleaned, report = clean_order_items(df)

    assert len(cleaned) == 1  # one duplicate removed, one bad price dropped
    assert report.duplicates_removed == 1


def test_clean_order_payments_defaults_missing_installments_to_one():
    df = pd.DataFrame(
        {
            "order_id": ["o1"],
            "payment_sequential": ["1"],
            "payment_type": [" Credit_Card "],
            "payment_installments": [None],
            "payment_value": ["100.0"],
        }
    )
    cleaned, _ = clean_order_payments(df)

    assert cleaned.iloc[0]["payment_installments"] == 1
    assert cleaned.iloc[0]["payment_type"] == "credit_card"

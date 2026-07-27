"""
Data quality checks against the loaded warehouse. Runnable standalone
(`pytest tests/`) or as an Airflow task — both paths just invoke pytest.
"""
from sqlalchemy import text

from tests.conftest import scalar

MIN_EXPECTED_ORDERS = 1
MAX_EXPECTED_ORDERS = 5_000_000  # sanity ceiling, not a real business limit


def test_fact_orders_row_count_in_range(conn):
    count = scalar(conn, "SELECT COUNT(*) FROM warehouse.fact_orders")
    assert MIN_EXPECTED_ORDERS <= count <= MAX_EXPECTED_ORDERS, (
        f"fact_orders row count {count} outside expected range"
    )


def test_no_nulls_in_required_fact_columns(conn):
    for column in ["order_id", "customer_key", "order_date_key"]:
        n_null = scalar(conn, f"SELECT COUNT(*) FROM warehouse.fact_orders WHERE {column} IS NULL")
        assert n_null == 0, f"{n_null} rows have NULL {column} in fact_orders"


def test_referential_integrity_customer_key(conn):
    n_orphans = scalar(
        conn,
        """
        SELECT COUNT(*) FROM warehouse.fact_orders f
        LEFT JOIN warehouse.dim_customer d ON f.customer_key = d.customer_key
        WHERE f.customer_key IS NOT NULL AND d.customer_key IS NULL
        """,
    )
    assert n_orphans == 0, f"{n_orphans} fact_orders rows reference a missing customer_key"


def test_referential_integrity_product_key(conn):
    n_orphans = scalar(
        conn,
        """
        SELECT COUNT(*) FROM warehouse.fact_orders f
        LEFT JOIN warehouse.dim_product d ON f.product_key = d.product_key
        WHERE f.product_key IS NOT NULL AND d.product_key IS NULL
        """,
    )
    assert n_orphans == 0, f"{n_orphans} fact_orders rows reference a missing product_key"


def test_referential_integrity_seller_key(conn):
    n_orphans = scalar(
        conn,
        """
        SELECT COUNT(*) FROM warehouse.fact_orders f
        LEFT JOIN warehouse.dim_seller d ON f.seller_key = d.seller_key
        WHERE f.seller_key IS NOT NULL AND d.seller_key IS NULL
        """,
    )
    assert n_orphans == 0, f"{n_orphans} fact_orders rows reference a missing seller_key"


def test_no_duplicate_order_line_items(conn):
    n_dupes = scalar(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT order_id, order_item_id, COUNT(*) AS c
            FROM warehouse.fact_orders
            GROUP BY order_id, order_item_id
            HAVING COUNT(*) > 1
        ) dupes
        """,
    )
    assert n_dupes == 0, f"{n_dupes} duplicate (order_id, order_item_id) pairs in fact_orders"


def test_delivery_days_never_negative(conn):
    n_negative = scalar(
        conn, "SELECT COUNT(*) FROM warehouse.fact_orders WHERE delivery_days < 0"
    )
    assert n_negative == 0, f"{n_negative} fact_orders rows have negative delivery_days"


def test_payment_value_never_negative(conn):
    n_negative = scalar(
        conn, "SELECT COUNT(*) FROM warehouse.fact_orders WHERE payment_value < 0"
    )
    assert n_negative == 0, f"{n_negative} fact_orders rows have negative payment_value"


def test_exactly_one_current_row_per_customer(conn):
    n_violations = scalar(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT customer_id, COUNT(*) AS c
            FROM warehouse.dim_customer
            WHERE is_current
            GROUP BY customer_id
            HAVING COUNT(*) != 1
        ) violations
        """,
    )
    assert n_violations == 0, f"{n_violations} customers do not have exactly one current dim row"

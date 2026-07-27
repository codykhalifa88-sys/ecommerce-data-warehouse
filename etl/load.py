"""
Run the SQL transform scripts in sql/transforms/ against the warehouse
schema, in dependency order: dim_date first (referenced by fact_orders),
then the remaining dimensions, then fact_orders last.

Every transform is an idempotent upsert (ON CONFLICT ... DO UPDATE, or the
SCD Type 2 expire-then-insert pattern for dim_customer), so re-running
load.py after a partial failure never duplicates or corrupts data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.utils.db import get_engine, get_logger

logger = get_logger("load")

TRANSFORMS_DIR = Path(__file__).resolve().parent.parent / "sql" / "transforms"

# (script filename, target warehouse table, source staging tables) in load order.
TRANSFORM_SEQUENCE: list[tuple[str, str, list[str]]] = [
    ("load_dim_date.sql", "dim_date", []),
    ("load_dim_geography.sql", "dim_geography", ["geolocation"]),
    ("load_dim_product.sql", "dim_product", ["products"]),
    ("load_dim_seller.sql", "dim_seller", ["sellers"]),
    ("load_dim_customer.sql", "dim_customer", ["customers"]),
    ("load_fact_orders.sql", "fact_orders", ["orders", "order_items", "order_payments", "order_reviews"]),
]


def _row_count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM warehouse.{table}")).scalar()


def _record_lineage(
    engine: Engine, source_tables: list[str], target_table: str, rows_in: int, rows_out: int
) -> None:
    with engine.begin() as conn:
        for source in source_tables or ["-"]:
            conn.execute(
                text(
                    """
                    INSERT INTO etl_control.pipeline_metadata
                        (source_table, target_table, rows_in, rows_out, stage)
                    VALUES (:source, :target, :rows_in, :rows_out, 'load')
                    """
                ),
                {"source": source, "target": target_table, "rows_in": rows_in, "rows_out": rows_out},
            )


def run_transform(engine: Engine, script_name: str, target_table: str, source_tables: list[str]) -> int:
    sql_path = TRANSFORMS_DIR / script_name
    sql_content = sql_path.read_text()

    rows_in = 0
    if source_tables:
        with engine.connect() as conn:
            rows_in = sum(
                conn.execute(text(f"SELECT COUNT(*) FROM staging.{t}")).scalar() for t in source_tables
            )

    logger.info("Running transform %s -> warehouse.%s", script_name, target_table)
    with engine.begin() as conn:
        conn.execute(text(sql_content))

    rows_out = _row_count(engine, target_table)
    _record_lineage(engine, source_tables, target_table, rows_in, rows_out)
    logger.info("warehouse.%s now has %d rows (source rows_in=%d)", target_table, rows_out, rows_in)
    return rows_out


def run_load(engine: Optional[Engine] = None) -> dict[str, int]:
    engine = engine or get_engine()
    results: dict[str, int] = {}
    for script_name, target_table, source_tables in TRANSFORM_SEQUENCE:
        try:
            results[target_table] = run_transform(engine, script_name, target_table, source_tables)
        except Exception:
            logger.exception("Transform %s failed", script_name)
            raise
    logger.info("Load complete: %s", results)
    return results


if __name__ == "__main__":
    run_load()

"""
Extract raw Olist CSVs into the `staging` schema in Postgres.

Design notes (see project README "Key Design Decisions"):
- Tables with a natural timestamp column (orders, order_reviews) are loaded
  incrementally: only rows newer than the watermark recorded in
  etl_control.load_log are appended to staging.
- order_items / order_payments are child records of orders with no timestamp
  of their own, so they're loaded incrementally by joining against the set
  of order_ids extracted this run.
- Reference/dimension-like tables (customers, products, sellers, geolocation,
  category translation) have no reliable "new row" signal in this dataset,
  so they're safely re-truncated and reloaded in full each run.
Either way, rerunning extract.py on the same day never duplicates staging rows.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.utils.db import get_engine, get_logger, raw_data_dir

logger = get_logger("extract")

EPOCH = datetime(1970, 1, 1)

FULL_REFRESH_TABLES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}

INCREMENTAL_TIMESTAMP_TABLES = {
    "orders": ("olist_orders_dataset.csv", "order_purchase_timestamp"),
    "order_reviews": ("olist_order_reviews_dataset.csv", "review_creation_date"),
}

CHILD_TABLES = {
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
}


def _get_watermark(engine: Engine, table_name: str) -> datetime:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT MAX(last_loaded_at) FROM etl_control.load_log "
                "WHERE table_name = :t AND status = 'success'"
            ),
            {"t": table_name},
        ).scalar()
    return result or EPOCH


def _log_run(
    engine: Engine,
    table_name: str,
    last_loaded_at: datetime,
    rows_loaded: int,
    status: str,
    started_at: datetime,
    error_message: Optional[str] = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO etl_control.load_log
                    (table_name, last_loaded_at, rows_loaded, status,
                     run_started_at, run_finished_at, error_message)
                VALUES
                    (:table_name, :last_loaded_at, :rows_loaded, :status,
                     :started_at, now(), :error_message)
                """
            ),
            {
                "table_name": table_name,
                "last_loaded_at": last_loaded_at,
                "rows_loaded": rows_loaded,
                "status": status,
                "started_at": started_at,
                "error_message": error_message,
            },
        )


def _load_full_refresh(engine: Engine, table: str, csv_name: str, data_dir: Path) -> int:
    started_at = datetime.now()
    df = pd.read_csv(data_dir / csv_name, dtype=str)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE staging.{table}"))
    df.to_sql(table, engine, schema="staging", if_exists="append", index=False)
    _log_run(engine, table, datetime.now(), len(df), "success", started_at)
    logger.info("staging.%s: full refresh, %d rows loaded", table, len(df))
    return len(df)


def _load_incremental_timestamp(
    engine: Engine, table: str, csv_name: str, ts_col: str, data_dir: Path
) -> tuple[int, pd.Series]:
    started_at = datetime.now()
    watermark = _get_watermark(engine, table)
    df = pd.read_csv(data_dir / csv_name, dtype=str)
    ts_parsed = pd.to_datetime(df[ts_col], errors="coerce")
    new_rows = df[ts_parsed > watermark]
    if len(new_rows) > 0:
        new_rows.to_sql(table, engine, schema="staging", if_exists="append", index=False)
        new_watermark = ts_parsed[ts_parsed > watermark].max()
    else:
        new_watermark = watermark
    _log_run(engine, table, new_watermark, len(new_rows), "success", started_at)
    logger.info(
        "staging.%s: incremental load, %d new rows since %s", table, len(new_rows), watermark
    )
    return len(new_rows), new_rows.get("order_id", pd.Series(dtype=str))


def _load_child_table(
    engine: Engine, table: str, csv_name: str, new_order_ids: pd.Series, data_dir: Path
) -> int:
    started_at = datetime.now()
    df = pd.read_csv(data_dir / csv_name, dtype=str)
    new_rows = df[df["order_id"].isin(set(new_order_ids))]
    if len(new_rows) > 0:
        new_rows.to_sql(table, engine, schema="staging", if_exists="append", index=False)
    _log_run(engine, table, datetime.now(), len(new_rows), "success", started_at)
    logger.info("staging.%s: incremental load (by order_id), %d new rows", table, len(new_rows))
    return len(new_rows)


def run_extract(data_dir: Optional[Path] = None) -> dict[str, int]:
    data_dir = data_dir or raw_data_dir()
    engine = get_engine()
    row_counts: dict[str, int] = {}

    for table, csv_name in FULL_REFRESH_TABLES.items():
        try:
            row_counts[table] = _load_full_refresh(engine, table, csv_name, data_dir)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extract staging.%s", table)
            _log_run(engine, table, datetime.now(), 0, "failed", datetime.now(), str(exc))
            raise

    new_order_ids = pd.Series(dtype=str)
    for table, (csv_name, ts_col) in INCREMENTAL_TIMESTAMP_TABLES.items():
        try:
            n_rows, order_ids = _load_incremental_timestamp(engine, table, csv_name, ts_col, data_dir)
            row_counts[table] = n_rows
            if table == "orders":
                new_order_ids = order_ids
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extract staging.%s", table)
            _log_run(engine, table, datetime.now(), 0, "failed", datetime.now(), str(exc))
            raise

    for table, csv_name in CHILD_TABLES.items():
        try:
            row_counts[table] = _load_child_table(engine, table, csv_name, new_order_ids, data_dir)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extract staging.%s", table)
            _log_run(engine, table, datetime.now(), 0, "failed", datetime.now(), str(exc))
            raise

    logger.info("Extract complete: %s", row_counts)
    return row_counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract raw Olist CSVs into staging tables")
    parser.add_argument("--data-dir", type=str, default=None, help="Override RAW_DATA_DIR")
    args = parser.parse_args()
    run_extract(Path(args.data_dir) if args.data_dir else None)

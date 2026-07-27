"""
Clean and type-cast staged Olist data, writing cleaned frames back into
staging tables (in place) so sql/transforms/*.sql can load them directly
into the warehouse.

Handles, per the project brief:
- null handling (drop / impute / flag, decided per column)
- type fixing (dates, numerics)
- deduplication on natural keys
- category name standardization via the translation table
- city/state casing + whitespace normalization

Produces a CleaningReport per table: rows in, rows out, nulls handled,
duplicates removed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.utils.db import get_engine, get_logger

logger = get_logger("clean")


@dataclass
class CleaningReport:
    table: str
    rows_in: int
    rows_out: int
    nulls_handled: int = 0
    duplicates_removed: int = 0
    notes: list[str] = field(default_factory=list)

    def log(self) -> None:
        logger.info(
            "[%s] rows_in=%d rows_out=%d nulls_handled=%d duplicates_removed=%d notes=%s",
            self.table,
            self.rows_in,
            self.rows_out,
            self.nulls_handled,
            self.duplicates_removed,
            "; ".join(self.notes) if self.notes else "-",
        )


def _standardize_text(series: pd.Series) -> pd.Series:
    return series.str.strip().str.lower()


def clean_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    nulls_handled = 0
    notes: list[str] = []

    df = df.drop_duplicates(subset=["customer_id"])
    duplicates_removed = rows_in - len(df)

    before = df["customer_city"].isna().sum() + df["customer_state"].isna().sum()
    df["customer_city"] = _standardize_text(df["customer_city"].fillna("unknown"))
    df["customer_state"] = df["customer_state"].str.strip().str.upper().fillna("UNKNOWN")
    nulls_handled += int(before)
    if before:
        notes.append("filled missing city/state with 'unknown'/'UNKNOWN'")

    df["customer_zip_code_prefix"] = df["customer_zip_code_prefix"].str.strip()

    report = CleaningReport(
        "customers", rows_in, len(df), nulls_handled, duplicates_removed, notes
    )
    return df, report


def clean_products(df: pd.DataFrame, translation: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    notes: list[str] = []

    df = df.drop_duplicates(subset=["product_id"])
    duplicates_removed = rows_in - len(df)

    nulls_before = df["product_category_name"].isna().sum()
    df["product_category_name"] = df["product_category_name"].fillna("unknown")

    translation = translation.rename(
        columns={"product_category_name_english": "category_name_en"}
    )
    df = df.merge(translation, on="product_category_name", how="left")
    unmatched = df["category_name_en"].isna().sum()
    df["category_name_en"] = df["category_name_en"].fillna(df["product_category_name"])
    if unmatched:
        notes.append(f"{unmatched} categories had no English translation, kept original name")

    for col in ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]:
        n_missing = df[col].isna().sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        median = df[col].median()
        df[col] = df[col].fillna(median)
        if n_missing:
            notes.append(f"imputed {n_missing} missing {col} with median ({median:.1f})")

    nulls_handled = int(nulls_before) + sum(
        df[c].isna().sum() for c in ["product_weight_g"]
    )  # representative count; per-column detail is in notes

    report = CleaningReport(
        "products", rows_in, len(df), nulls_handled, duplicates_removed, notes
    )
    return df, report


def clean_sellers(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    df = df.drop_duplicates(subset=["seller_id"])
    duplicates_removed = rows_in - len(df)

    nulls_before = df["seller_city"].isna().sum() + df["seller_state"].isna().sum()
    df["seller_city"] = _standardize_text(df["seller_city"].fillna("unknown"))
    df["seller_state"] = df["seller_state"].str.strip().str.upper().fillna("UNKNOWN")

    report = CleaningReport(
        "sellers", rows_in, len(df), int(nulls_before), duplicates_removed
    )
    return df, report


def clean_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    notes: list[str] = []

    df = df.drop_duplicates(subset=["order_id"])
    duplicates_removed = rows_in - len(df)

    date_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    nulls_handled = 0
    for col in date_cols:
        n_missing = df[col].isna().sum()
        df[col] = pd.to_datetime(df[col], errors="coerce")
        nulls_handled += int(n_missing)

    # Orders missing a purchase timestamp are unusable for fact loading — drop, don't impute a date.
    before_drop = len(df)
    df = df.dropna(subset=["order_purchase_timestamp"])
    dropped = before_drop - len(df)
    if dropped:
        notes.append(f"dropped {dropped} orders with no purchase timestamp")

    df["order_status"] = df["order_status"].str.strip().str.lower()

    report = CleaningReport(
        "orders", rows_in, len(df), nulls_handled, duplicates_removed, notes
    )
    return df, report


def clean_order_items(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    df = df.drop_duplicates(subset=["order_id", "order_item_id"])
    duplicates_removed = rows_in - len(df)

    nulls_before = df["price"].isna().sum() + df["freight_value"].isna().sum()
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce").fillna(0)
    before_drop = len(df)
    df = df.dropna(subset=["price"])
    notes = []
    dropped = before_drop - len(df)
    if dropped:
        notes.append(f"dropped {dropped} line items with unparseable price")

    report = CleaningReport(
        "order_items", rows_in, len(df), int(nulls_before), duplicates_removed, notes
    )
    return df, report


def clean_order_payments(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    df = df.drop_duplicates(subset=["order_id", "payment_sequential"])
    duplicates_removed = rows_in - len(df)

    nulls_before = df["payment_value"].isna().sum()
    df["payment_value"] = pd.to_numeric(df["payment_value"], errors="coerce").fillna(0)
    df["payment_installments"] = pd.to_numeric(df["payment_installments"], errors="coerce").fillna(1).astype(int)
    df["payment_type"] = df["payment_type"].str.strip().str.lower().fillna("unknown")

    report = CleaningReport(
        "order_payments", rows_in, len(df), int(nulls_before), duplicates_removed
    )
    return df, report


def clean_order_reviews(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    rows_in = len(df)
    df = df.drop_duplicates(subset=["order_id"], keep="last")
    duplicates_removed = rows_in - len(df)

    nulls_before = df["review_score"].isna().sum()
    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    notes = []
    before_drop = len(df)
    df = df.dropna(subset=["review_score"])
    dropped = before_drop - len(df)
    if dropped:
        notes.append(f"dropped {dropped} reviews with unparseable score")

    report = CleaningReport(
        "order_reviews", rows_in, len(df), int(nulls_before), duplicates_removed, notes
    )
    return df, report


TABLE_CLEANERS = {
    "customers": clean_customers,
    "sellers": clean_sellers,
    "orders": clean_orders,
    "order_items": clean_order_items,
    "order_payments": clean_order_payments,
    "order_reviews": clean_order_reviews,
}


def run_clean(engine: Optional[Engine] = None) -> list[CleaningReport]:
    engine = engine or get_engine()
    reports: list[CleaningReport] = []

    # _loaded_at is extract-step bookkeeping, not cleaning input — dropped
    # before any joins so it can't collide (e.g. products x translation both
    # carry it, which would otherwise suffix to _loaded_at_x/_loaded_at_y
    # and break the write-back). The table's own DEFAULT now() reapplies it.
    products_raw = pd.read_sql("SELECT * FROM staging.products", engine).drop(
        columns=["_loaded_at", "category_name_en"]
    )
    translation_raw = pd.read_sql(
        "SELECT * FROM staging.product_category_name_translation", engine
    ).drop(columns=["_loaded_at"])
    products_clean, report = clean_products(products_raw, translation_raw)
    _write_back(engine, "products", products_clean)
    reports.append(report)
    report.log()

    for table, cleaner in TABLE_CLEANERS.items():
        raw = pd.read_sql(f"SELECT * FROM staging.{table}", engine).drop(columns=["_loaded_at"])
        cleaned, report = cleaner(raw)
        _write_back(engine, table, cleaned)
        reports.append(report)
        report.log()

    total_in = sum(r.rows_in for r in reports)
    total_out = sum(r.rows_out for r in reports)
    logger.info("Clean complete: %d rows in, %d rows out across %d tables", total_in, total_out, len(reports))
    return reports


def _write_back(engine: Engine, table: str, df: pd.DataFrame) -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE staging.{table}"))
    df.to_sql(table, engine, schema="staging", if_exists="append", index=False)


if __name__ == "__main__":
    run_clean()

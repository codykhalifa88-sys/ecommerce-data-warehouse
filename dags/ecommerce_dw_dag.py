"""
Airflow DAG: ecommerce_dw_pipeline

extract_raw -> clean_data -> load_dimensions (parallel, dim_date first)
            -> load_fact -> run_data_quality_checks -> refresh_dashboard_data

Runs daily. Failure on any task retries twice with a 5 minute delay, then
logs an alert (and pings Slack if SLACK_WEBHOOK_URL is configured).
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger("ecommerce_dw_dag")

PROJECT_ROOT = os.environ.get("AIRFLOW_PROJECT_ROOT", "/opt/airflow")


def _on_failure_alert(context) -> None:
    """Log the failure and notify Slack if a webhook is configured.

    A placeholder webhook check is intentional: in production this would
    post to #data-alerts so the on-call engineer sees the failed task
    without having to check the Airflow UI.
    """
    task_id = context["task_instance"].task_id
    dag_id = context["task_instance"].dag_id
    exception = context.get("exception")
    logger.error("Task %s in DAG %s failed: %s", task_id, dag_id, exception)

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set — would notify #data-alerts in production")
        return

    import json
    import urllib.request

    payload = json.dumps(
        {"text": f":rotating_light: `{dag_id}.{task_id}` failed: {exception}"}
    ).encode()
    req = urllib.request.Request(
        webhook_url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to post Slack alert")


default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": _on_failure_alert,
}


def _run_module(module: str) -> None:
    result = subprocess.run(
        ["python", "-m", module], cwd=PROJECT_ROOT, capture_output=True, text=True
    )
    logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"{module} failed with exit code {result.returncode}")


def _run_sql_transform(script_name: str, target_table: str, source_tables: list[str]) -> None:
    import sys

    sys.path.insert(0, PROJECT_ROOT)
    from etl.load import run_transform
    from etl.utils.db import get_engine

    run_transform(get_engine(), script_name, target_table, source_tables)


def extract_raw() -> None:
    _run_module("etl.extract")


def clean_data() -> None:
    _run_module("etl.clean")


def load_dim_date() -> None:
    _run_sql_transform("load_dim_date.sql", "dim_date", [])


def load_dim_geography() -> None:
    _run_sql_transform("load_dim_geography.sql", "dim_geography", ["geolocation"])


def load_dim_product() -> None:
    _run_sql_transform("load_dim_product.sql", "dim_product", ["products"])


def load_dim_seller() -> None:
    _run_sql_transform("load_dim_seller.sql", "dim_seller", ["sellers"])


def load_dim_customer() -> None:
    _run_sql_transform("load_dim_customer.sql", "dim_customer", ["customers"])


def load_fact() -> None:
    _run_sql_transform(
        "load_fact_orders.sql",
        "fact_orders",
        ["orders", "order_items", "order_payments", "order_reviews"],
    )


def run_data_quality_checks() -> None:
    result = subprocess.run(
        ["pytest", "tests/test_data_quality.py", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError("Data quality checks failed — see logs above")


def refresh_dashboard_data() -> None:
    """Materialize dashboard-ready aggregates. The dashboard queries
    warehouse tables directly at this data volume, so this is a no-op
    placeholder for a materialized-view refresh in a larger deployment."""
    logger.info("Dashboard reads live from warehouse.* — nothing to materialize at this scale")


with DAG(
    dag_id="ecommerce_dw_pipeline",
    description="Extract, clean, and load Olist e-commerce data into the star schema warehouse",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ecommerce", "warehouse", "etl"],
) as dag:
    t_extract = PythonOperator(task_id="extract_raw", python_callable=extract_raw)
    t_clean = PythonOperator(task_id="clean_data", python_callable=clean_data)

    t_dim_date = PythonOperator(task_id="load_dim_date", python_callable=load_dim_date)
    t_dim_geo = PythonOperator(task_id="load_dim_geography", python_callable=load_dim_geography)
    t_dim_product = PythonOperator(task_id="load_dim_product", python_callable=load_dim_product)
    t_dim_seller = PythonOperator(task_id="load_dim_seller", python_callable=load_dim_seller)
    t_dim_customer = PythonOperator(task_id="load_dim_customer", python_callable=load_dim_customer)

    t_fact = PythonOperator(task_id="load_fact", python_callable=load_fact)
    t_dq_checks = PythonOperator(task_id="run_data_quality_checks", python_callable=run_data_quality_checks)
    t_refresh_dashboard = PythonOperator(task_id="refresh_dashboard_data", python_callable=refresh_dashboard_data)

    dimension_tasks = [t_dim_geo, t_dim_product, t_dim_seller, t_dim_customer]

    t_extract >> t_clean >> t_dim_date
    t_dim_date >> dimension_tasks
    dimension_tasks >> t_fact
    t_fact >> t_dq_checks >> t_refresh_dashboard

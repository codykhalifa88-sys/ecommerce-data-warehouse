"""
Generate a small synthetic Olist-shaped dataset into data/raw/, so the
pipeline is runnable end-to-end without a Kaggle account.

This is NOT a substitute for the real dataset — it exists purely so CI and
a first local run have something to chew on. For the real, messy, ~100K-order
dataset that makes the cleaning/DQ work meaningful, download from
https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and place the
CSVs in data/raw/ (they'll overwrite these sample files).

Uses only the standard library so it can run before `pip install -r
requirements.txt` (e.g. as the very first command after cloning).
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

N_CUSTOMERS = 600
N_PRODUCTS = 150
N_SELLERS = 60
N_ORDERS = 1000

BRAZIL_STATES_CITIES = [
    ("SP", "sao paulo"), ("SP", "campinas"), ("RJ", "rio de janeiro"),
    ("MG", "belo horizonte"), ("RS", "porto alegre"), ("PR", "curitiba"),
    ("BA", "salvador"), ("SC", "florianopolis"), ("PE", "recife"),
    ("CE", "fortaleza"), ("DF", "brasilia"), ("GO", "goiania"),
]

CATEGORIES = [
    ("beleza_saude", "health_beauty"),
    ("informatica_acessorios", "computers_accessories"),
    ("cama_mesa_banho", "bed_bath_table"),
    ("esporte_lazer", "sports_leisure"),
    ("moveis_decoracao", "furniture_decor"),
    ("brinquedos", "toys"),
    ("telefonia", "telephony"),
    ("relogios_presentes", "watches_gifts"),
    ("automotivo", "auto"),
    ("cool_stuff", "cool_stuff"),
]

ORDER_STATUSES = ["delivered"] * 8 + ["shipped"] * 1 + ["canceled"] * 1

PAYMENT_TYPES = ["credit_card", "boleto", "voucher", "debit_card"]


def _rand_zip() -> str:
    return f"{random.randint(1000, 99999):05d}"


def _rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def generate() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- customers ----
    customers = []
    for i in range(N_CUSTOMERS):
        state, city = random.choice(BRAZIL_STATES_CITIES)
        customers.append(
            {
                "customer_id": f"cust_{i:05d}",
                "customer_unique_id": f"uniq_{i:05d}",
                "customer_zip_code_prefix": _rand_zip(),
                "customer_city": city if random.random() > 0.02 else "",  # inject some nulls
                "customer_state": state,
            }
        )
    _write_csv(
        "olist_customers_dataset.csv",
        customers,
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"],
    )

    # ---- geolocation ----
    geolocation = []
    for _, (state, city) in [(i, random.choice(BRAZIL_STATES_CITIES)) for i in range(500)]:
        geolocation.append(
            {
                "geolocation_zip_code_prefix": _rand_zip(),
                "geolocation_lat": f"{random.uniform(-33.0, 2.0):.6f}",
                "geolocation_lng": f"{random.uniform(-73.0, -35.0):.6f}",
                "geolocation_city": city,
                "geolocation_state": state,
            }
        )
    _write_csv(
        "olist_geolocation_dataset.csv",
        geolocation,
        ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"],
    )

    # ---- products ----
    products = []
    for i in range(N_PRODUCTS):
        cat_pt, _ = random.choice(CATEGORIES)
        products.append(
            {
                "product_id": f"prod_{i:05d}",
                "product_category_name": cat_pt if random.random() > 0.03 else "",
                "product_name_lenght": str(random.randint(10, 60)),
                "product_description_lenght": str(random.randint(50, 2000)),
                "product_photos_qty": str(random.randint(1, 8)),
                "product_weight_g": str(random.randint(100, 20000)) if random.random() > 0.02 else "",
                "product_length_cm": str(random.randint(5, 100)),
                "product_height_cm": str(random.randint(5, 100)),
                "product_width_cm": str(random.randint(5, 100)),
            }
        )
    _write_csv(
        "olist_products_dataset.csv",
        products,
        [
            "product_id", "product_category_name", "product_name_lenght",
            "product_description_lenght", "product_photos_qty", "product_weight_g",
            "product_length_cm", "product_height_cm", "product_width_cm",
        ],
    )

    # ---- sellers ----
    sellers = []
    for i in range(N_SELLERS):
        state, city = random.choice(BRAZIL_STATES_CITIES)
        sellers.append(
            {
                "seller_id": f"seller_{i:05d}",
                "seller_zip_code_prefix": _rand_zip(),
                "seller_city": city,
                "seller_state": state,
            }
        )
    _write_csv(
        "olist_sellers_dataset.csv", sellers, ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]
    )

    # ---- category translation ----
    translation = [{"product_category_name": pt, "product_category_name_english": en} for pt, en in CATEGORIES]
    _write_csv(
        "product_category_name_translation.csv",
        translation,
        ["product_category_name", "product_category_name_english"],
    )

    # ---- orders + items + payments + reviews ----
    orders, order_items, order_payments, order_reviews = [], [], [], []
    window_start = datetime(2017, 1, 1)
    window_end = datetime(2018, 8, 1)

    for i in range(N_ORDERS):
        order_id = f"order_{i:06d}"
        customer = random.choice(customers)
        status = random.choice(ORDER_STATUSES)
        purchase_ts = _rand_date(window_start, window_end)
        approved_ts = purchase_ts + timedelta(hours=random.randint(1, 48))
        carrier_ts = approved_ts + timedelta(days=random.randint(1, 3))
        estimated_delivery = purchase_ts + timedelta(days=random.randint(10, 25))

        delivered_ts = ""
        if status == "delivered":
            actual_delivery_days = random.randint(3, 30)
            delivered_dt = carrier_ts + timedelta(days=actual_delivery_days)
            delivered_ts = delivered_dt.strftime("%Y-%m-%d %H:%M:%S")

        orders.append(
            {
                "order_id": order_id,
                "customer_id": customer["customer_id"],
                "order_status": status,
                "order_purchase_timestamp": purchase_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "order_approved_at": approved_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_carrier_date": carrier_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_customer_date": delivered_ts,
                "order_estimated_delivery_date": estimated_delivery.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        n_items = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
        for item_idx in range(1, n_items + 1):
            product = random.choice(products)
            seller = random.choice(sellers)
            order_items.append(
                {
                    "order_id": order_id,
                    "order_item_id": str(item_idx),
                    "product_id": product["product_id"],
                    "seller_id": seller["seller_id"],
                    "shipping_limit_date": (purchase_ts + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
                    "price": f"{random.uniform(15, 500):.2f}",
                    "freight_value": f"{random.uniform(5, 60):.2f}",
                }
            )

        payment_value = round(random.uniform(30, 1200), 2)
        order_payments.append(
            {
                "order_id": order_id,
                "payment_sequential": "1",
                "payment_type": random.choice(PAYMENT_TYPES),
                "payment_installments": str(random.randint(1, 10)),
                "payment_value": f"{payment_value:.2f}",
            }
        )

        if status == "delivered" and random.random() > 0.1:
            score = random.choices([1, 2, 3, 4, 5], weights=[5, 5, 10, 30, 50])[0]
            order_reviews.append(
                {
                    "review_id": f"review_{i:06d}",
                    "order_id": order_id,
                    "review_score": str(score),
                    "review_comment_title": "",
                    "review_comment_message": "" if score >= 4 else "atraso na entrega",
                    "review_creation_date": (delivered_ts or purchase_ts.strftime("%Y-%m-%d %H:%M:%S")),
                    "review_answer_timestamp": (delivered_ts or purchase_ts.strftime("%Y-%m-%d %H:%M:%S")),
                }
            )

    _write_csv(
        "olist_orders_dataset.csv",
        orders,
        [
            "order_id", "customer_id", "order_status", "order_purchase_timestamp",
            "order_approved_at", "order_delivered_carrier_date",
            "order_delivered_customer_date", "order_estimated_delivery_date",
        ],
    )
    _write_csv(
        "olist_order_items_dataset.csv",
        order_items,
        ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"],
    )
    _write_csv(
        "olist_order_payments_dataset.csv",
        order_payments,
        ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
    )
    _write_csv(
        "olist_order_reviews_dataset.csv",
        order_reviews,
        [
            "review_id", "order_id", "review_score", "review_comment_title",
            "review_comment_message", "review_creation_date", "review_answer_timestamp",
        ],
    )

    print(
        f"Generated sample data in {OUT_DIR}: "
        f"{len(customers)} customers, {len(products)} products, {len(sellers)} sellers, "
        f"{len(orders)} orders, {len(order_items)} order_items, "
        f"{len(order_payments)} payments, {len(order_reviews)} reviews"
    )


def _write_csv(filename: str, rows: list[dict], fieldnames: list[str]) -> None:
    path = OUT_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    generate()

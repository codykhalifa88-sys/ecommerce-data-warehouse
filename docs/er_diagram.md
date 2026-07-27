# ER Diagram

GitHub renders this Mermaid diagram natively — no external tool needed to view it.
For a PNG (e.g. to embed in a slide deck), paste the DDL from `sql/ddl/02_warehouse_schema.sql`
into [dbdiagram.io](https://dbdiagram.io) or run this file through the [Mermaid Live Editor](https://mermaid.live)
and export as `docs/er_diagram.png`.

```mermaid
erDiagram
    dim_date ||--o{ fact_orders : "order_date_key"
    dim_date ||--o{ fact_orders : "delivery_date_key"
    dim_customer ||--o{ fact_orders : "customer_key"
    dim_product ||--o{ fact_orders : "product_key"
    dim_seller ||--o{ fact_orders : "seller_key"

    dim_date {
        int date_key PK
        date full_date
        int day
        int month
        text month_name
        int quarter
        int year
        text day_of_week
        boolean is_weekend
    }

    dim_customer {
        int customer_key PK
        text customer_id
        text customer_city
        text customer_state
        text customer_zip_prefix
        date valid_from
        date valid_to
        boolean is_current
    }

    dim_product {
        int product_key PK
        text product_id
        text category_name
        text category_name_en
        numeric weight_g
        numeric length_cm
        numeric height_cm
        numeric width_cm
    }

    dim_seller {
        int seller_key PK
        text seller_id
        text seller_city
        text seller_state
    }

    dim_geography {
        int geo_key PK
        text zip_code_prefix
        text city
        text state
        numeric lat
        numeric lng
    }

    fact_orders {
        int order_key PK
        text order_id
        text order_item_id
        int customer_key FK
        int product_key FK
        int seller_key FK
        int order_date_key FK
        int delivery_date_key FK
        text order_status
        numeric price
        numeric freight_value
        numeric payment_value
        text payment_type
        int installments
        int review_score
        int delivery_days
        boolean is_late
    }
```

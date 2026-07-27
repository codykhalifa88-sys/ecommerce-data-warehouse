"""
Streamlit dashboard for the e-commerce warehouse. Reads live from
warehouse.* — at ~100K orders no materialized aggregate layer is needed.

Color usage follows a fixed 2-3 color system: blue for the primary revenue
series and ranked-magnitude bars, orange as the secondary hue when a second
magnitude series appears alongside it. Colors are assigned by role, not
cycled per chart.
"""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run dashboard/app.py` puts dashboard/ on sys.path, not the
# project root, so the etl package next to it isn't importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl.utils.db import get_engine

COLOR_BLUE = "#2a78d6"
COLOR_ORANGE = "#eb6834"
COLOR_AQUA = "#1baf7a"
CATEGORICAL = [COLOR_BLUE, COLOR_ORANGE, COLOR_AQUA, "#eda100", "#e87ba4"]

st.set_page_config(page_title="E-Commerce Data Warehouse", layout="wide")


@st.cache_resource
def _engine():
    return get_engine()


@st.cache_data(ttl=600)
def load_fact() -> pd.DataFrame:
    query = """
        SELECT
            f.order_id, f.order_item_id, f.price, f.freight_value, f.payment_value,
            f.payment_type, f.installments, f.review_score, f.delivery_days, f.is_late,
            f.order_status,
            d.full_date AS order_date, d.year, d.month, d.month_name,
            c.customer_state, c.customer_city,
            p.category_name_en
        FROM warehouse.fact_orders f
        JOIN warehouse.dim_date d ON d.date_key = f.order_date_key
        LEFT JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
        LEFT JOIN warehouse.dim_product p ON p.product_key = f.product_key
        WHERE f.order_status NOT IN ('canceled', 'unavailable')
    """
    return pd.read_sql(query, _engine(), parse_dates=["order_date"])


def _base_chart_layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7")
    fig.update_yaxes(showgrid=True, gridcolor="#e1e0d9", zeroline=False)
    return fig


st.title("E-Commerce Data Warehouse")
st.caption("Olist Brazilian e-commerce — order, delivery, and revenue analytics")

df = load_fact()

if df.empty:
    st.warning("No data in warehouse.fact_orders yet — run the ETL pipeline first (see README).")
    st.stop()

with st.sidebar:
    st.header("Filters")
    min_date, max_date = df["order_date"].min().date(), df["order_date"].max().date()
    date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

    states = sorted(df["customer_state"].dropna().unique())
    selected_states = st.multiselect("State", states, default=[])

    categories = sorted(df["category_name_en"].dropna().unique())
    selected_categories = st.multiselect("Category", categories, default=[])

filtered = df.copy()
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[(filtered["order_date"].dt.date >= start) & (filtered["order_date"].dt.date <= end)]
if selected_states:
    filtered = filtered[filtered["customer_state"].isin(selected_states)]
if selected_categories:
    filtered = filtered[filtered["category_name_en"].isin(selected_categories)]

filtered["revenue"] = filtered["price"] + filtered["freight_value"]

# ---- KPI cards ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Revenue", f"R$ {filtered['revenue'].sum():,.0f}")
col2.metric("Total Orders", f"{filtered['order_id'].nunique():,}")
col3.metric("Avg Delivery Days", f"{filtered['delivery_days'].mean():.1f}")
col4.metric("Avg Review Score", f"{filtered['review_score'].mean():.2f}")

st.divider()

left, right = st.columns(2)

# ---- Revenue over time (single series -> blue, no legend needed) ----
with left:
    monthly = (
        filtered.groupby(filtered["order_date"].dt.to_period("M"))["revenue"]
        .sum()
        .reset_index()
    )
    monthly["order_date"] = monthly["order_date"].dt.to_timestamp()
    fig = go.Figure(
        go.Scatter(
            x=monthly["order_date"],
            y=monthly["revenue"],
            mode="lines+markers",
            line=dict(color=COLOR_BLUE, width=2),
            marker=dict(size=6, color=COLOR_BLUE),
            hovertemplate="%{x|%b %Y}<br>R$ %{y:,.0f}<extra></extra>",
        )
    )
    fig = _base_chart_layout(fig, "Revenue Over Time")
    st.plotly_chart(fig, use_container_width=True)

# ---- Top categories (ranked magnitude -> single hue) ----
with right:
    top_categories = (
        filtered.groupby("category_name_en")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .sort_values()
    )
    fig = go.Figure(
        go.Bar(
            x=top_categories.values,
            y=top_categories.index,
            orientation="h",
            marker=dict(color=COLOR_BLUE),
            hovertemplate="%{y}<br>R$ %{x:,.0f}<extra></extra>",
        )
    )
    fig = _base_chart_layout(fig, "Top 10 Categories by Revenue")
    st.plotly_chart(fig, use_container_width=True)

left2, right2 = st.columns(2)

# ---- Delivery performance by state (magnitude -> orange, second series role) ----
with left2:
    by_state = (
        filtered.dropna(subset=["delivery_days"])
        .groupby("customer_state")["delivery_days"]
        .mean()
        .sort_values(ascending=False)
        .head(15)
        .sort_values()
    )
    fig = go.Figure(
        go.Bar(
            x=by_state.values,
            y=by_state.index,
            orientation="h",
            marker=dict(color=COLOR_ORANGE),
            hovertemplate="%{y}<br>%{x:.1f} days<extra></extra>",
        )
    )
    fig = _base_chart_layout(fig, "Avg Delivery Days by State")
    st.plotly_chart(fig, use_container_width=True)

# ---- % late deliveries by state ----
with right2:
    late_by_state = (
        filtered.dropna(subset=["is_late"])
        .groupby("customer_state")["is_late"]
        .mean()
        .mul(100)
        .sort_values(ascending=False)
        .head(15)
        .sort_values()
    )
    fig = go.Figure(
        go.Bar(
            x=late_by_state.values,
            y=late_by_state.index,
            orientation="h",
            marker=dict(color=COLOR_AQUA),
            hovertemplate="%{y}<br>%{x:.1f}% late<extra></extra>",
        )
    )
    fig = _base_chart_layout(fig, "% Late Deliveries by State")
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Filtered order detail")
st.dataframe(
    filtered[
        ["order_id", "order_date", "customer_state", "category_name_en", "revenue", "delivery_days", "is_late", "review_score"]
    ].sort_values("order_date", ascending=False),
    use_container_width=True,
    height=300,
)

import json
import os
from datetime import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_NAME = "Mob Price Monitor"
OUTPUT_TAB = "price_daily"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


@st.cache_resource
def get_client() -> gspread.Client:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is missing.")

    info = json.loads(raw)
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(credentials)


@st.cache_data(ttl=300)
def load_price_daily() -> pd.DataFrame:
    client = get_client()
    ws = client.open(SHEET_NAME).worksheet(OUTPUT_TAB)
    records = ws.get_all_records()
    df = pd.DataFrame(records)

    if df.empty:
        return df

    df["crawl_date"] = pd.to_datetime(df["crawl_date"], errors="coerce").dt.date
    df["crawl_time"] = pd.to_datetime(df["crawl_time"], errors="coerce").dt.time

    for col in ["price", "original_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    platforms = sorted(x for x in df["platform"].dropna().unique())
    brands = sorted(x for x in df["brand"].dropna().unique())
    models = sorted(x for x in df["model"].dropna().unique())

    st.sidebar.header("Filters")
    selected_platforms = st.sidebar.multiselect("Platform", platforms, default=platforms)
    selected_brands = st.sidebar.multiselect("Brand", brands, default=brands)
    selected_models = st.sidebar.multiselect("Model", models, default=models)

    min_date = df["crawl_date"].min()
    max_date = df["crawl_date"].max()
    date_range = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    filtered = df[
        df["platform"].isin(selected_platforms)
        & df["brand"].isin(selected_brands)
        & df["model"].isin(selected_models)
    ]

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered = filtered[(filtered["crawl_date"] >= start) & (filtered["crawl_date"] <= end)]

    return filtered


def latest_price_table(df: pd.DataFrame) -> pd.DataFrame:
    latest = (
        df.sort_values(by=["crawl_date", "crawl_time"], ascending=[False, False])
        .groupby(["platform", "brand", "model", "product_url"], as_index=False)
        .first()
    )
    return latest[["platform", "brand", "model", "price", "original_price", "stock_status", "crawl_date", "product_url"]]


def main() -> None:
    st.set_page_config(page_title="Mobile Price Monitor", layout="wide")
    st.title("📱 Mobile Phone Price Monitor")

    try:
        df = load_price_daily()
    except Exception as exc:
        st.error(f"Failed to load Google Sheet data: {exc}")
        return

    if df.empty:
        st.info("No data found in price_daily yet.")
        return

    filtered = apply_filters(df)

    st.subheader("Latest Price Snapshot")
    latest_df = latest_price_table(filtered)
    st.dataframe(latest_df, use_container_width=True)

    st.subheader("Price Trend")
    trend_df = (
        filtered.dropna(subset=["price", "crawl_date"])
        .groupby(["crawl_date", "brand", "model"], as_index=False)["price"]
        .mean()
    )
    if trend_df.empty:
        st.info("No price points available for the selected filters.")
    else:
        trend_df["series"] = trend_df["brand"] + " - " + trend_df["model"]
        pivot_df = trend_df.pivot(index="crawl_date", columns="series", values="price")
        st.line_chart(pivot_df)

    st.subheader("Export")
    csv_data = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download filtered data (CSV)",
        data=csv_data,
        file_name=f"price_daily_{datetime.now().date().isoformat()}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List

import gspread
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials

LOGGER = logging.getLogger(__name__)

SHEET_NAME = "Mob Price Monitor"
INPUT_TAB = "sku_master"
OUTPUT_TAB = "price_daily"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def get_gspread_client() -> gspread.Client:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is missing.")

    info = json.loads(raw)
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(credentials)


def parse_priceoye(url: str) -> Dict[str, str]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    price = ""
    original_price = ""
    stock_status = ""

    # Try several selectors to reduce breakage from minor markup changes.
    price_selectors = [
        "span.price-box__price",
        ".price h4",
        "div.price > h4",
        "span.current-price",
    ]
    for selector in price_selectors:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            price = clean_price(node.get_text(" ", strip=True))
            if price:
                break

    original_selectors = [
        "span.price-box__old-price",
        ".price del",
        "div.price del",
        "span.old-price",
    ]
    for selector in original_selectors:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            original_price = clean_price(node.get_text(" ", strip=True))
            if original_price:
                break

    stock_selectors = [
        ".stock-status",
        ".availability",
        "span[class*='stock']",
        "div[class*='stock']",
    ]
    for selector in stock_selectors:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            stock_status = node.get_text(" ", strip=True)
            break

    # Fallback from page text for common terms.
    if not stock_status:
        page_text = soup.get_text(" ", strip=True).lower()
        if "out of stock" in page_text:
            stock_status = "Out of Stock"
        elif "in stock" in page_text:
            stock_status = "In Stock"

    if not stock_status:
        stock_status = "Unknown"

    if not price:
        raise ValueError("Price not found in PriceOye page")

    return {
        "price": price,
        "original_price": original_price,
        "stock_status": stock_status,
    }


def clean_price(text: str) -> str:
    numeric = re.sub(r"[^\d.]", "", text)
    return numeric.strip(".")


def fetch_active_skus(ws: gspread.Worksheet) -> List[Dict[str, str]]:
    rows = ws.get_all_records()
    active_rows = []

    for row in rows:
        status = str(row.get("status", "")).strip().lower()
        product_url = str(row.get("product_url", "")).strip()
        if status == "active" and product_url:
            active_rows.append(
                {
                    "platform": str(row.get("platform", "")).strip(),
                    "brand": str(row.get("brand", "")).strip(),
                    "model": str(row.get("model", "")).strip(),
                    "product_url": product_url,
                }
            )

    return active_rows


def build_output_row(sku: Dict[str, str], parsed: Dict[str, str]) -> List[str]:
    now = datetime.now(timezone.utc)
    crawl_date = now.date().isoformat()
    crawl_time = now.strftime("%H:%M:%S")

    return [
        crawl_date,
        sku["platform"],
        sku["brand"],
        sku["model"],
        parsed.get("price", ""),
        parsed.get("original_price", ""),
        parsed.get("stock_status", ""),
        sku["product_url"],
        crawl_time,
    ]


def run_crawl() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    client = get_gspread_client()
    spreadsheet = client.open(SHEET_NAME)
    sku_ws = spreadsheet.worksheet(INPUT_TAB)
    out_ws = spreadsheet.worksheet(OUTPUT_TAB)

    active_skus = fetch_active_skus(sku_ws)
    LOGGER.info("Found %d active SKUs", len(active_skus))

    output_rows: List[List[str]] = []

    for sku in active_skus:
        url = sku["product_url"]
        platform = sku.get("platform", "")
        try:
            if platform.lower() != "priceoye" and "priceoye" not in url.lower():
                parsed = {
                    "price": "",
                    "original_price": "",
                    "stock_status": "Unsupported platform for parser",
                }
            else:
                parsed = parse_priceoye(url)
            LOGGER.info("Crawled %s | %s %s", url, sku.get("brand"), sku.get("model"))
        except Exception as exc:
            LOGGER.exception("Failed to crawl URL: %s", url)
            parsed = {
                "price": "",
                "original_price": "",
                "stock_status": f"ERROR: {exc}",
            }

        output_rows.append(build_output_row(sku, parsed))

    if output_rows:
        out_ws.append_rows(output_rows, value_input_option="USER_ENTERED")
        LOGGER.info("Appended %d rows to %s", len(output_rows), OUTPUT_TAB)
    else:
        LOGGER.info("No active SKUs to process; nothing appended.")


if __name__ == "__main__":
    run_crawl()

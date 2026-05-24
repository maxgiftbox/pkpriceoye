# Mobile Price Monitor (PriceOye + Google Sheets + Streamlit)

This project monitors mobile phone prices from **PriceOye**, stores daily crawl outputs into Google Sheets, and provides a Streamlit dashboard for filtering and trend analysis.

## Project Files

- `scraper.py` — Reads active SKUs from Google Sheet, crawls prices, and appends daily results.
- `app.py` — Streamlit dashboard for filters, latest price view, trend chart, and CSV export.
- `requirements.txt` — Python dependencies.

## Google Sheet Configuration

- **Google Sheet name:** `Mob Price Monitor`
- **Input tab:** `sku_master`
- **Output tab:** `price_daily`

### `sku_master` columns

`platform | brand | model | product_url | status`

### `price_daily` columns

`crawl_date | platform | brand | model | price | original_price | stock_status | product_url | crawl_time`

## Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set the Google service account JSON as an environment variable named `GOOGLE_SERVICE_ACCOUNT_JSON`.

### Linux/macOS

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
```

### Windows PowerShell

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
```

4. Share your Google Sheet (`Mob Price Monitor`) with the service account email.

## Run the scraper

```bash
python scraper.py
```

What it does:
- Connects to Google Sheets using `gspread` + `google-auth`.
- Reads `sku_master` and processes only rows where `status = active`.
- Crawls PriceOye URLs with `requests` + `BeautifulSoup` using a browser user-agent.
- Parses `price`, `original_price`, and `stock_status`.
- If parsing fails, it still appends a row with blank price and an error message in `stock_status`.
- Appends all crawl results to `price_daily`.

## Run the Streamlit dashboard

```bash
streamlit run app.py
```

Dashboard features:
- Filters by platform, brand, model, and date range.
- Latest price snapshot table.
- Price trend line chart.
- CSV download for filtered data.

## Notes

- PriceOye page markup can change over time; parser selectors may need updates.
- `crawl_date` is recorded in UTC date and `crawl_time` in UTC time.

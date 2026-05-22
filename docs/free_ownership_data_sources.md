# Free Ownership And Short-Interest Data Sources

This project uses free sources first and keeps live fetching opt-in where a
full-universe run could be slow or rate-limited.

## Official Free Sources

- SEC EDGAR APIs
  - Covers company submissions, XBRL company facts, 13F filings, and Form 3/4/5 insider filings.
  - Current setup: SEC 13F trend enrichment is enabled through `institutional_data`.
  - Current setup: SEC Form 4 insider transaction enrichment is available through `insider_data`, but disabled by default because coverage is sparse unless candidate CIKs are supplied.
  - Limitation: 13F is manager-reported quarterly holdings, not a clean real-time total institutional ownership percentage.
  - Link: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

- FINRA Equity Short Interest
  - Covers bimonthly short-interest positions, average daily share volume, and days to cover.
  - Current setup: `short_interest_data` is enabled and reads local files from `data/raw/short_interest`.
  - Live endpoint: `https://api.finra.org/data/group/otcMarket/name/EquityShortInterest`
  - Current setup: `fetch_live` defaults to `false`; turn it on only for a single ticker or a small candidate set.
  - Links:
    - https://www.finra.org/finra-data/browse-catalog/equity-short-interest
    - https://www.finra.org/sites/default/files/Equity_Short_Interest_Data_File_Download_API.pdf

## Free But Unofficial Fallbacks

- yfinance / Yahoo Finance
  - Used for price, volume, market cap, and optional quote-summary fallback.
  - Current setup additionally stores `floatShares` as `shares_float` and `heldPercentInsiders` as `insider_ownership` when Yahoo returns them.
  - Limitation: unofficial, rate-limited, and not guaranteed to be complete or stable.

## Fields Added By The Setup

- `short_interest`
- `short_interest_previous`
- `short_interest_change`
- `short_interest_change_pct`
- `short_average_daily_volume`
- `short_days_to_cover`
- `short_percent_float` when a float-share denominator exists
- `short_percent_shares_outstanding` when shares outstanding exists
- `short_interest_settlement_date`
- `short_interest_source`
- `shares_float` from yfinance fallback when available
- `insider_ownership` from yfinance fallback when available

## Practical Use

- Broad screener run:
  - Put downloaded FINRA CSV/JSON files under `data/raw/short_interest`.
  - Run `./canslimsepa/bin/python run_screener.py --mode enrich --config config/config.json`.

- Single ticker live lookup:
  - Temporarily set `short_interest_data.fetch_live` to `true`.
  - Run `./canslimsepa/bin/python run_screener.py --mode analyze --ticker FN --config config/config.json`.

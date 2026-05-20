# Growth Stock Screener

A Python application for screening growth stocks with CAN SLIM criteria using SEC EDGAR financial data and yfinance market data.

> This project is a research/screening aid only. Do not make investment decisions solely from its output.

## Features

- Downloads SEC EDGAR submissions and company facts data
- Parses XBRL company facts into financial metrics such as EPS growth, revenue growth, margins, ROE, and debt-to-equity
- Enriches companies with price/relative-strength, liquidity, volume, market-direction, optional 13F institutional flow, and optional Form 4 insider data
- Supports profile-based screening configurations
- Exports results to CSV

## Installation

```bash
git clone https://github.com/Yooh-an/gss.git
cd gss
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The repository also includes a convenience `./screener` wrapper. If a local `canslimsepa` virtual environment is absent, it falls back to `python3`.

## Quick Start

Run the full default workflow:

```bash
./screener all
```

Run steps individually:

```bash
./screener status
./screener download
./screener parse
./screener enrich
./screener screen
./screener tv-export
```

For day-to-day use, either open the interactive terminal menu:

```bash
python terminal.py
```

or inspect status/run missing stages from the CLI:

```bash
python run_screener.py --mode status --config config/base.json --profile canslim_pure
python run_screener.py --mode update --config config/base.json --profile canslim_watchlist
python run_screener.py --mode analyze --ticker STRL --config config/base.json --profile canslim_pure
python run_screener.py --mode tv-export --config config/base.json --profile canslim_pure
```

Equivalent Python entrypoint:

```bash
python run_screener.py --mode download --config config/config.json
python run_screener.py --mode parse --config config/config.json
python run_screener.py --mode enrich --config config/config.json
python run_screener.py --mode screen --config config/config.json
python run_screener.py --mode status --config config/config.json
python run_screener.py --mode analyze --ticker STRL --config config/config.json
```

## Profiles

Shared settings live in `config/base.json`; strategy overlays live in `config/profiles/`.

Examples:

```bash
python run_screener.py --mode enrich --config config/base.json --profile canslim_pure
python run_screener.py --mode screen --config config/base.json --profile canslim_pure

python run_screener.py --mode screen --config config/base.json --profile canslim_watchlist
```

Available profiles:

- `canslim_pure`: closer to canonical CAN SLIM requirements, including institutional sponsorship
- `canslim_watchlist`: broader candidate list; institutional data contributes to score/report but is not a hard requirement

## Configuration Shape

Current configuration uses these top-level sections:

```json
{
  "sec_api": {
    "user_agent": "Your Name (your.email@example.com)",
    "rate_limit_delay": 0.1
  },
  "data_paths": {
    "raw_data_dir": "data/raw",
    "processed_data_dir": "data/processed",
    "output_file": "data/processed/results.csv"
  },
  "download_settings": {
    "company_limit": null,
    "force_download": false
  },
  "screening_criteria": {
    "quarterly_eps_growth": 0.25,
    "annual_eps_cagr": 0.25,
    "revenue_growth": 0.25,
    "profit_margin": 0.10,
    "roe": 0.17,
    "debt_to_equity": 2.0,
    "outperform_sp500": true,
    "min_market_cap": 300000000
  },
  "leadership_criteria": {},
  "market_direction": {},
  "supply_demand_criteria": {},
  "institutional_criteria": {},
  "institutional_data": {
    "enabled": true,
    "raw_13f_dir": "data/raw/institutional_13f",
    "cusip_ticker_mapping": "data/processed/cusip_ticker_mapping.csv",
    "manager_ciks": ["0001067983", "0000102909", "0001364742"]
  },
  "insider_data": {
    "enabled": true,
    "fetch_live": true,
    "raw_form4_dir": "data/raw/insider_form4",
    "company_ciks": [],
    "limit_per_company": 20
  },
  "pattern_criteria": {}
}
```

## TradingView Export

After running `screen`, export the current profile's candidates into TradingView-ready operation files:

```bash
python run_screener.py --mode tv-export --config config/base.json --profile canslim_pure
```

This writes two sibling files next to the profile result CSV:

- `*_tradingview_watchlist.txt`: one uppercase ticker per line for watchlist import/MCP watchlist automation
- `*_tradingview_review_plan.json`: sorted candidates, trade-plan levels, and suggested TradingView MCP actions for chart review, screenshots, and alerts

The export intentionally does not replace the core SEC/yfinance scoring pipeline. It is an operating layer for final TradingView chart validation and alert setup.

## Free SEC 13F Institutional Data

The optional `institutional_data` section supports CAN SLIM's institutional sponsorship check without paid APIs.

- If `manager_ciks` is provided, `enrich` downloads the latest and previous `13F-HR` information tables for those SEC manager CIKs.
- If `manager_ciks` is empty, it reads local XML files from `data/raw/institutional_13f/current` and `data/raw/institutional_13f/previous`.
- A `cusip_ticker_mapping` CSV/JSON can map 13F CUSIPs to tickers. Without it, the fallback is normalized issuer/company-name matching. The collector also includes helpers to infer mapping suggestions and export mapping coverage for manual review.
- Enriched fields include `institutional_holders`, `institutional_value`, `institutional_holders_qoq_change`, `institutional_value_qoq_change`, `new_holder_count`, `increased_holder_count`, `decreased_holder_count`, `exited_holder_count`, `institutional_accumulation_score`, and `top_accumulating_managers`.

## SEC Form 4 Insider Data

The optional `insider_data` section adds insider buy/sell activity from free SEC Form 4 XML filings.

- If `company_ciks` is provided, `enrich` downloads recent Form 4 filings for those companies.
- If `company_ciks` is empty, it uses CIKs from the current company list.
- Enriched fields include `insider_buy_count_90d`, `insider_sell_count_90d`, `gross_insider_buy_value_90d`, `gross_insider_sell_value_90d`, `net_insider_buy_value_90d`, and `insider_signal`.
- This is a supporting signal only; CAN SLIM screening remains centered on earnings, leadership, sponsorship, supply/demand, and market direction.

## CAN SLIM Scoring

Passing candidates are enriched with a component scorecard:

- `c_score`, `a_score`, `n_score`, `s_score`, `l_score`, `i_score`, `m_score`
- `canslim_score`, `score_band`
- `pass_reasons`, `fail_reasons`

Default result sorting prefers `canslim_score` when present. `create_report()` writes both CSV and a sibling Markdown report summarizing top candidates, component scores, trade plan levels, 13F flow, insider signal, and pass/fail reasons.

## Leadership Enhancements

Price enrichment includes CAN SLIM leadership metrics such as `rs_rating`, `rs_line_near_high`, `rs_line_new_high`, `rs_line_pct_from_high`, `industry_rs_rank`, `industry_stock_rank`, `industry_group_leader`, and `industry_stock_leader`.

## Project Structure

```text
config/                 Configuration files and strategy profiles
docs/                   Architecture and SEC API notes
src/api/                SEC and SimFin client modules
src/collectors/         SEC/company data collection
src/parsers/            Submissions and company facts parsing
src/enrichers/          Market, RS, volume, and institutional enrichment
src/screeners/          Financial and price screeners
src/utils/              Shared utilities
tests/                  Unit and integration tests
run_screener.py         Main Python CLI wrapper
screener                Shell convenience wrapper
```

Runtime data and logs are intentionally ignored by Git:

- `data/`
- `logs/`
- virtual environments such as `.venv/`, `venv/`, `canslimsepa/`
- coverage/cache artifacts

## Development

Run tests:

```bash
pytest -q
```

Current expected result:

```text
93 passed
```

## References

- [SEC EDGAR API Documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [CAN SLIM Investment Strategy](https://www.investors.com/ibd-university/can-slim/)

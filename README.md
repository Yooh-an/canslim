# Growth Stock Screener

A Python application for screening growth stocks with CAN SLIM and SEPA-style criteria using SEC EDGAR financial data and yfinance market data.

> This project is a research/screening aid only. Do not make investment decisions solely from its output.

## Features

- Downloads SEC EDGAR submissions and company facts data
- Parses XBRL company facts into financial metrics such as EPS growth, revenue growth, margins, ROE, and debt-to-equity
- Enriches companies with price/relative-strength, liquidity, volume, market-direction, and optional institutional data
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
./screener download
./screener parse
./screener enrich
./screener screen
```

Equivalent Python entrypoint:

```bash
python run_screener.py --mode download --config config/config.json
python run_screener.py --mode parse --config config/config.json
python run_screener.py --mode enrich --config config/config.json
python run_screener.py --mode screen --config config/config.json
```

## Profiles

Shared settings live in `config/base.json`; strategy overlays live in `config/profiles/`.

Examples:

```bash
python run_screener.py --mode enrich --config config/base.json --profile canslim_pure
python run_screener.py --mode screen --config config/base.json --profile canslim_pure

python run_screener.py --mode enrich --config config/base.json --profile canslim_hybrid
python run_screener.py --mode screen --config config/base.json --profile canslim_hybrid
```

Available profiles:

- `canslim_pure`: closer to canonical CAN SLIM requirements
- `canslim_hybrid`: CAN SLIM growth filters plus SEPA-style technical setup filters

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
  "pattern_criteria": {}
}
```

## Project Structure

```text
config/                 Configuration files and strategy profiles
docs/                   Architecture and SEC API notes
src/api/                SEC/FMP client modules
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
41 passed
```

## References

- [SEC EDGAR API Documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [CAN SLIM Investment Strategy](https://www.investors.com/ibd-university/can-slim/)
- [Mark Minervini's Trend Template](https://www.minervini.com/blog/index.php/trend-template/)

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

Open the local browser dashboard:

```bash
./screener web --open
```

If you omit `--open`, visit `http://127.0.0.1:8765` manually. The dashboard reuses local pipeline
outputs under `data/processed`, adds best-effort live market indicators and
headlines, and exposes daily research workflows:

- market direction, major index/macro indicators, and broad market headlines
- active profile strategy lens with key growth, quality, leadership, liquidity thresholds and required/optional gate summary
- profile matrix for comparing strategy outputs, candidate counts, top scores, freshness, one-click profile switching, and per-profile screen/rerun actions
- all-profile screening sweep from the profile matrix or diagnostics to refresh every configured strategy output in one background job
- in-app research-only disclosure with result/market freshness, mirrored into JSON review, TradingView, dossier, and workspace exports
- trading-session-aware market freshness that handles weekends and US market holidays separately from calendar age
- daily Action Center with market posture, setup counts, priority candidates, one-click review queueing, and pipeline/review tasks
- first-screen Decision Brief that combines data freshness, market exposure, setup mix, candidate quality, review queue, and risk guardrails into a session call-to-action
- date-based session journal for market thesis, watchlist focus, risk notes, and post-session review, included in session reports and workspace snapshots
- one-ticker CAN SLIM analysis, research brief, setup notes, and trade-plan levels overlaid on the price chart using the existing `analyze` logic
- single-stock research dossier JSON export containing the active analysis, strategy lens, data-health state, and evidence metadata
- account-equity and risk-per-trade preferences with position sizing in the trade plan
- configurable review guardrails for maximum planned capital, total queue risk, open-position stop risk, and planned/open concentration
- sortable profile-based CAN SLIM screener tables from the generated result CSV files
- saved screener views for recurring search, score, setup, and sort combinations
- side-by-side Candidate Compare from selected screener rows with JSON export for final shortlist review
- current screener view CSV export that preserves search, score, setup, and sort filters
- bulk-add of the currently visible screener candidates into the review queue
- pasted ticker/watchlist import into the review queue with per-symbol analysis and failure reporting
- pasted last-price updates for existing review items to refresh open-position P/L and stop-risk alerts in bulk
- review queue sorting, status/priority filtering, manual high/normal/low priority, risk summary, total planned risk, planned capital, unsized candidates, and inline entry/stop edits
- saved review queue views for recurring triage filters, status/priority/tag slices, and sort combinations
- review queue tags with tag filtering, searchable notes/tags, and CSV/JSON/TradingView export support
- review aging controls for stale active/ready items so old decisions are surfaced before they silently expire
- review risk ledger with prioritized risk actions, guardrail usage, planned and open-position sector/setup concentration, status-level risk/capital breakdown, and largest planned positions
- per-ticker pre-buy checklist for weekly chart, daily chart, volume, market alignment, and defined risk; incomplete ready items are surfaced in the risk summary, blocker drilldown, and CSV/JSON/TradingView readiness blockers
- bought/sold position lifecycle capture for fill price, share count, execution date, manual last-price overrides, exit price/date/reason, realized P/L/R, win-rate/drawdown performance journal, open-position portfolio risk, current-price P/L/R monitoring, stop-risk alerts, and reversible alert acknowledgement
- selected review-item bulk status/priority/tag changes and removal for fast daily triage
- profile-specific review queues, decision states, notes, and position-sized CSV/JSON/ticker exports atomically persisted under `data/web_workspace`
- TradingView-ready JSON review-plan exports from the curated review queue, including notes, trade levels, sizing, and alert actions
- generated artifact downloads for the active profile's result CSV, Markdown report, TradingView watchlist, and TradingView review plan, with SHA-256 response headers for audit checks
- two-step review-queue clearing with server-side `confirm=clear` protection for destructive actions
- recent review activity log with undo for bulk status changes, remove/bulk-remove, and clear events, included in JSON exports
- CSV review exports escape formula-like text fields while preserving numeric values
- persisted workspace preferences for the active profile, screener filters, saved screener views, review filters, saved review views, and risk guardrails
- workspace snapshot JSON export/import with pre-import impact preview, server-side confirmation for destructive imports/restores, automatic atomic retained pre-import backups with SHA-256 fingerprints, fingerprint-pinned backup restores and backup deletion, corrupt-store quarantine during backup restore/import, in-app backup download/restore/delete controls, searchable/filterable recent workspace operation audit trail with JSON export, sensitive download/export audit events, restore impact preview, active profile, preferences, review queue, sizing summary, and evidence metadata
- profile-scoped browser fallback storage, sanitized external/API download links, no-store static responses, and explicit 404s for missing assets to avoid stale or hidden broken UI files
- keyboard-accessible skip navigation and focus-managed workspace import/backup dialogs with ESC close and focus return
- visible sync/offline status, app version/revision runtime badge, bounded browser API timeouts, server client-socket timeouts, write API rate limits, and JSON write body size limits, request IDs on all server responses/errors, runtime run ID/uptime health metadata, HEAD-compatible health checks, per-session CSRF tokens for write APIs and header-gated sensitive downloads, strict CSP without inline-style requirements, Permissions-Policy, and Cross-Origin browser safety headers
- system diagnostics for config/static assets, visible web security posture controls, browser security policy readiness, writable and parseable workspace/audit stores, workspace free space, interrupted atomic-write temp files with in-app cleanup, profile outputs, artifacts, and pipeline command readiness, with corrupt workspace stores blocked before overwrite and routed to audit repair or backup restore recovery
- release readiness gates plus deployment handoff commands and a machine-readable `/api/readiness` endpoint that roll up app bundle, browser/security posture, access control, workspace integrity, pipeline state, profile outputs, and downloadable artifacts before operator use
- in-app recent request trace and browser event panel plus redacted support bundle JSON export for troubleshooting release readiness, diagnostics, artifact metadata, provenance, recent request metadata, rate-limited redacted browser error events, job history, and recent workspace audit state without absolute local paths, HTTP query strings/bodies, browser storage contents, review notes, journal text, workspace snapshots, or raw store contents
- session runbook in Data Operations for pipeline freshness, market tape age, review queue, risk plan, generated outputs, and dossier checkpoints
- daily Markdown/JSON session report export for disclosure, freshness, strategy lens, action center, review risk, artifacts, jobs, and evidence
- background job status, cancellation, recent execution history, and one-click `tv-export` generation for pipeline runs
- local-only dashboard binding by default; non-loopback hosts require explicit `--allow-remote`, fail-closed auth can be required, and repeated Basic Auth failures are temporarily throttled
- Host header validation plus explicit same-origin `Origin` requirements for write APIs on local and remote bindings to reduce DNS rebinding/cross-origin request risk
- actionable data-health findings for missing/stale outputs plus auditable evidence log with source-file freshness, row counts, and short SHA-256 fingerprints
- candidate quality coverage for score, price, pivot, stop, growth, RS, setup, sector, volume, and institutional fields with ticker-level trade-plan gaps
- background pipeline actions for the next recommended step, enrich, and screen
- optional HTTP Basic authentication for the local dashboard when exposing it beyond a private single-user machine

Equivalent Python entrypoint:

```bash
python run_screener.py --mode web --port 8765 --open
```

Run steps individually:

```bash
./screener status
./screener download
./screener parse
./screener enrich
./screener screen
./screener tv-export
./screener profile-sweep
./screener web
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
python run_screener.py --mode profile-sweep --config config/config.json
python run_screener.py --mode web --port 8765
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
  "broker_api": {
    "enabled": true,
    "provider": "kis",
    "use_for_single_ticker": true,
    "app_key_env": "KIS_APP_KEY",
    "app_secret_env": "KIS_APP_SECRET",
    "adjusted_price": true
  },
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

## Optional Broker Price Provider

Single-ticker analysis can use Korea Investment & Securities Open API before
falling back to Yahoo/yfinance. Set the read-only KIS credentials in your shell
or `.env`; no credentials are committed.

```bash
export KIS_APP_KEY='your-app-key'
export KIS_APP_SECRET='your-app-secret'
python run_screener.py --mode analyze --ticker TSLA --config config/base.json --profile canslim_pure
```

The integration calls KIS overseas daily price history with adjusted prices
enabled, caches the token under `data/raw/kis_token.json`, and caches returned
OHLCV history under `data/raw/price_history`. It is used only for single-ticker
price history, benchmark history, and current-price refresh. Full-universe
leadership runs still use the existing Yahoo/yfinance batch path.

## TradingView Export

After running `screen`, export the current profile's candidates into TradingView-ready operation files:

```bash
python run_screener.py --mode tv-export --config config/base.json --profile canslim_pure
```

This writes two sibling files next to the profile result CSV:

- `*_tradingview_watchlist.txt`: one uppercase ticker per line for watchlist import/MCP watchlist automation
- `*_tradingview_review_plan.json`: sorted candidates, trade-plan levels, and suggested TradingView MCP actions for chart review, screenshots, and alerts

The export intentionally does not replace the core SEC/yfinance scoring pipeline. It is an operating layer for final TradingView chart validation and alert setup.

The web dashboard can also export the curated review queue as a TradingView JSON plan from the Review Queue export selector. That export reflects manual entry/stop edits, decision state, review notes, position sizing, and generated alert levels.

## Dashboard Access

The browser dashboard binds to `127.0.0.1` by default. For normal local use:

```bash
./screener web --open
```

If you intentionally bind it to a remote interface, add your own network controls and/or require Basic Auth. Prefer the environment variable form so the password is not placed directly in shell history or process arguments:

```bash
CANSLIM_DASHBOARD_AUTH='trader:change-this-password' ./screener web --host 0.0.0.0 --allow-remote --require-auth
```

The CLI also accepts `--auth USER:PASSWORD` for short-lived local use and `--auth-env ENV_VAR` if your deployment uses a different secret name. Use `--require-auth` for remote/container launches that should fail closed when credentials are missing. Do not expose the dashboard directly to the public internet.

## Container Runtime

The repository includes a production-oriented Docker image definition for repeatable dashboard runs:

```bash
docker build -t canslim-sepa .
docker run --rm -p 8765:8765 \
  -e CANSLIM_DASHBOARD_AUTH='trader:change-this-password' \
  -v "$PWD/data:/app/data" \
  canslim-sepa
```

The container runs as a non-root user, exposes port `8765`, includes a healthcheck against `/api/readiness`, and starts with `--require-auth`, so it exits instead of serving the dashboard if `CANSLIM_DASHBOARD_AUTH` is missing. The readiness probe uses the same release gates shown in Data Operations and the support bundle. It relies on `.dockerignore` to keep `.env`, Git metadata, caches, virtualenvs, logs, and runtime data out of the build context. Mount `data/` when you want dashboard state, processed results, and workspace backups to persist across container restarts.

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
src/web/                Local web dashboard API and background job server
tests/                  Unit and integration tests
web/                    Browser dashboard HTML/CSS/JavaScript
Dockerfile              Container runtime for the browser dashboard
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
316 passed
```

## References

- [SEC EDGAR API Documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [CAN SLIM Investment Strategy](https://www.investors.com/ibd-university/can-slim/)

# Growth Stock Screener

A Python application that automatically screens growth stocks based on CAN SLIM and Minervini strategies using the SEC EDGAR API.

## Key Features

- Corporate financial data collection through SEC EDGAR API
- Calculation of key financial metrics including quarterly/annual growth rates, ROE, and profit margins
- Stock performance analysis using yfinance
- Support for customizable screening criteria
- Export screening results in CSV format

## Installation

1. Install Python 3.8 or higher
2. Clone the project
```bash
git clone [repository_url]
cd growth-stock-screener
```

3. Create and activate virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate    # Windows
```

4. Install dependencies
```bash
pip install -r requirements.txt
```

## Usage

### 1. Download Data
```bash
python growth_stock_screener.py --mode download
```

### 2. Parse Data
```bash
python growth_stock_screener.py --mode parse
```

### 3. Screen Stocks
```bash
python growth_stock_screener.py --mode screen --config config.json
```

### Configuration File Example (config.json)
```json
{
  "criteria": {
    "quarterly_eps_growth": 0.25,
    "annual_eps_cagr": 0.25,
    "revenue_growth": 0.25,
    "profit_margin": 0.10,
    "roe": 0.15,
    "debt_to_equity": 1.0,
    "outperform_sp500": true,
    "institutional_ownership": 0.50
  },
  "fmp_api_key": "optional_key_here",
  "output_path": "results.csv"
}
```

## Project Structure

```
growth-stock-screener/
├── config/             # Configuration files
├── data/              # Data storage
│   ├── raw/          # Raw data
│   └── processed/    # Processed data
├── docs/              # Documentation
├── logs/              # Log files
├── src/               # Source code
│   ├── utils/        # Utility modules
│   └── growth_stock_screener.py
├── tests/             # Test code
├── requirements.txt   # Dependencies
└── README.md
```

## Data Processing Workflow

1. Download corporate financial data from SEC EDGAR API
2. Extract required financial metrics by parsing XBRL data
3. Calculate growth rates and financial ratios
4. Integrate stock price data through yfinance
5. Screen stocks based on user-defined criteria
6. Export results to CSV file

## How to Contribute

1. Submit Issues: Report bugs or suggest features
2. Submit Pull Requests: Improve code or implement new features
3. Improve Documentation: README, comments, technical docs

## References

- [SEC EDGAR API Documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [CAN SLIM Investment Strategy](https://www.investors.com/ibd-university/can-slim/)
- [Mark Minervini's Trend Template](https://www.minervini.com/blog/index.php/trend-template/)

## Important Notes

- The SEC EDGAR API applies rate limits to excessive requests. This application implements appropriate rate limiting.
- Do not base investment decisions solely on the results of this tool; always conduct additional research and seek professional advice.

## License

This project is distributed under the MIT License. See the LICENSE file for more information.
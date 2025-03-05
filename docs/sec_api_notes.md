# SEC EDGAR API Research Notes

## Overview
The SEC EDGAR system provides access to corporate filings and financial data through various API endpoints. For our Growth Stock Screener application, we need to understand and utilize specific endpoints to collect the necessary financial data.

## Key API Endpoints

### 1. EDGAR Submissions
- **Endpoint**: `https://data.sec.gov/submissions/submissions.zip`
- **Description**: This ZIP file contains metadata about all company submissions to the SEC.
- **Data Format**: JSON
- **Key Information**: 
  - CIK numbers (Central Index Key - unique identifier for each filer)
  - Company names
  - Ticker symbols
  - Latest filings

### 2. Company Facts
- **Endpoint**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit CIK}.json`
- **Description**: Contains structured financial data (facts) for a specific company.
- **Data Format**: JSON
- **Key Information**:
  - US GAAP taxonomy concepts
  - Time series of values for each concept
  - Quarterly and annual reports data

### 3. Company Concept
- **Endpoint**: `https://data.sec.gov/api/xbrl/companyconcept/CIK{10-digit CIK}/us-gaap/{concept}.json`
- **Description**: Contains all values for a specific financial concept for a given company.
- **Data Format**: JSON
- **Key Information**:
  - Historic values for a specific financial concept
  - Units and context information

## API Usage Guidelines

### Rate Limiting
- SEC limits requests to 10 requests per second
- Recommended delay between requests: 0.1 seconds
- User-Agent header is required and should include:
  - Name of the requesting organization/individual
  - Email address

### Headers

User-Agent: Name (email@example.com) Accept-Encoding: gzip, deflate Host: data.sec.gov

## Data Extraction Strategy

1. Download and extract the submissions.zip file
2. Extract list of active companies with their CIKs and tickers
3. For each relevant company:
   - Download company facts data
   - Extract required financial metrics:
     - EPS (us-gaap:EarningsPerShareDiluted)
     - Revenue (us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax / us-gaap:Revenue)
     - Net Income (us-gaap:NetIncomeLoss)
     - Assets (us-gaap:Assets)
     - Liabilities (us-gaap:Liabilities)
     - Shareholders' Equity (us-gaap:StockholdersEquity)

## Challenges and Considerations

1. **Data Consistency**: Companies may use different taxonomy elements for the same concept
2. **Missing Data**: Not all companies report all metrics
3. **Data Volume**: Company facts files can be large (several MB each)
4. **API Reliability**: Need to handle temporary failures and implement retry logic

## References
- [SEC API Documentation](https://www.sec.gov/edgar/sec-api-documentation)
- [SEC Developer Resources](https://www.sec.gov/developer)
- [XBRL US GAAP Taxonomy](https://xbrl.us/xbrl-taxonomy/2022-us-gaap/)
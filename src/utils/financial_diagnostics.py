"""
Financial Data Diagnostic Tool

This module helps diagnose issues with financial data collection and processing.
"""

import os
import json
import glob
import pandas as pd
from typing import Dict, Any, List, Tuple
from pathlib import Path

from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("financial_diagnostics")

class FinancialDiagnostics:
    """
    Provides diagnostics for financial data processing
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize diagnostics tool
        
        Args:
            config: Application configuration
        """
        self.config = config
        
        # Get data paths
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        self.financial_data_dir = os.path.join(self.raw_data_dir, "financial_data")
        
        # Ensure financial data directory exists
        Path(self.financial_data_dir).mkdir(parents=True, exist_ok=True)
    
    def diagnose_data_structure(self) -> Dict[str, Any]:
        """
        Check data structure and availability
        
        Returns:
            Dictionary with diagnostic information
        """
        results = {
            "directories": {},
            "files": {},
            "content": {}
        }
        
        # Check directories
        dirs_to_check = [
            self.raw_data_dir,
            self.processed_data_dir,
            self.company_facts_dir,
            self.financial_data_dir
        ]
        
        for dir_path in dirs_to_check:
            exists = os.path.exists(dir_path)
            is_dir = os.path.isdir(dir_path) if exists else False
            is_writable = os.access(dir_path, os.W_OK) if exists else False
            
            results["directories"][dir_path] = {
                "exists": exists,
                "is_directory": is_dir,
                "is_writable": is_writable
            }
        
        # Check files
        files_to_check = [
            os.path.join(self.processed_data_dir, "companies_list.json"),
            os.path.join(self.processed_data_dir, "financial_metrics.parquet"),
            os.path.join(self.processed_dir, "results.csv")
        ]
        
        for file_path in files_to_check:
            exists = os.path.exists(file_path)
            is_file = os.path.isfile(file_path) if exists else False
            size = os.path.getsize(file_path) if exists and is_file else 0
            is_readable = os.access(file_path, os.R_OK) if exists else False
            
            results["files"][file_path] = {
                "exists": exists,
                "is_file": is_file,
                "size_bytes": size,
                "is_readable": is_readable
            }
        
        # Check content of company facts dir
        company_facts_files = glob.glob(os.path.join(self.company_facts_dir, "CIK*.json"))
        results["content"]["company_facts"] = {
            "file_count": len(company_facts_files),
            "sample_files": company_facts_files[:5] if company_facts_files else []
        }
        
        # Check content of financial data dir
        financial_data_files = glob.glob(os.path.join(self.financial_data_dir, "*.*"))
        results["content"]["financial_data"] = {
            "file_count": len(financial_data_files),
            "sample_files": financial_data_files[:5] if financial_data_files else []
        }
        
        return results
    
    def check_company_facts_sample(self, sample_size: int = 3) -> Dict[str, Any]:
        """
        Examine a sample of company facts files
        
        Args:
            sample_size: Number of files to sample
            
        Returns:
            Dictionary with sample contents
        """
        company_facts_files = glob.glob(os.path.join(self.company_facts_dir, "CIK*.json"))
        
        if not company_facts_files:
            return {"error": "No company facts files found"}
        
        # Take a random sample
        import random
        sample_files = random.sample(company_facts_files, min(sample_size, len(company_facts_files)))
        
        results = {}
        
        for file_path in sample_files:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                cik = os.path.basename(file_path).replace('CIK', '').replace('.json', '')
                
                # Extract basic info
                entity_name = data.get('entityName', 'N/A')
                ticker = data.get('tickers', ['N/A'])[0] if isinstance(data.get('tickers', []), list) and data.get('tickers') else 'N/A'
                
                # Check for financial data
                us_gaap = data.get('facts', {}).get('us-gaap', {})
                
                key_fields = {
                    "has_eps": any(tag in us_gaap for tag in ["EarningsPerShareDiluted", "EarningsPerShareBasic"]),
                    "has_revenue": any(tag in us_gaap for tag in ["Revenue", "Revenues", "SalesRevenueNet"]),
                    "has_assets": "Assets" in us_gaap,
                    "has_equity": any(tag in us_gaap for tag in ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"])
                }
                
                results[cik] = {
                    "file": file_path,
                    "name": entity_name,
                    "ticker": ticker,
                    "key_fields": key_fields,
                    "us_gaap_tags": list(us_gaap.keys())[:10] if us_gaap else []  # First 10 tags
                }
                
            except Exception as e:
                results[os.path.basename(file_path)] = {"error": str(e)}
        
        return results
    
    def diagnose_financial_metrics(self) -> Dict[str, Any]:
        """
        Check financial metrics calculation issues
        
        Returns:
            Dictionary with diagnostic information
        """
        metrics_file = os.path.join(self.processed_data_dir, "financial_metrics.parquet")
        
        if not os.path.exists(metrics_file):
            return {"error": "Financial metrics file does not exist"}
        
        try:
            # Load metrics
            df = pd.read_parquet(metrics_file)
            
            # Basic stats
            row_count = len(df)
            col_count = len(df.columns)
            
            # Check key columns
            key_columns = ['cik', 'name', 'ticker']
            missing_key_columns = [col for col in key_columns if col not in df.columns]
            
            # Check financial metrics
            financial_columns = ['quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth', 
                                'profit_margin', 'roe', 'debt_to_equity']
            
            metrics_stats = {}
            
            for col in financial_columns:
                if col in df.columns:
                    non_null = df[col].notna().sum()
                    metrics_stats[col] = {
                        "exists": True,
                        "non_null_count": int(non_null),
                        "coverage": float(non_null) / row_count if row_count > 0 else 0
                    }
                else:
                    metrics_stats[col] = {
                        "exists": False,
                        "non_null_count": 0,
                        "coverage": 0
                    }
            
            return {
                "file": metrics_file,
                "row_count": row_count,
                "column_count": col_count,
                "columns": list(df.columns),
                "missing_key_columns": missing_key_columns,
                "metrics_stats": metrics_stats,
                "sample_rows": df.head(3).to_dict(orient='records') if not df.empty else []
            }
            
        except Exception as e:
            return {
                "error": f"Error reading financial metrics file: {str(e)}",
                "file": metrics_file
            }
    
    def create_financial_data_folder(self) -> Dict[str, Any]:
        """
        Create financial_data folder with example data structure
        
        Returns:
            Dictionary with success status
        """
        try:
            financial_data_dir = self.financial_data_dir
            Path(financial_data_dir).mkdir(parents=True, exist_ok=True)
            
            # Create a README.md file explaining the folder purpose
            readme_path = os.path.join(financial_data_dir, "README.md")
            with open(readme_path, 'w') as f:
                f.write("""# Financial Data

This folder contains additional financial data that supplements the SEC EDGAR data.
It is used by the Growth Stock Screener application to enrich the analysis with:

1. Quarterly financial statements (parsed from 10-Q reports)
2. Annual financial statements (parsed from 10-K reports)
3. Stock price performance data
4. Institutional ownership data

Files in this directory are automatically created and updated by the application
during the data collection process.
""")
            
            # Create placeholder structure
            placeholder_dirs = [
                "quarterly",
                "annual",
                "market_data",
                "ownership"
            ]
            
            for dir_name in placeholder_dirs:
                dir_path = os.path.join(financial_data_dir, dir_name)
                Path(dir_path).mkdir(exist_ok=True)
                
                # Add empty .keep file to maintain directory in git
                with open(os.path.join(dir_path, ".keep"), 'w') as f:
                    f.write("")
            
            return {
                "success": True,
                "created_dirs": [os.path.join(financial_data_dir, d) for d in placeholder_dirs],
                "readme": readme_path
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

def run_diagnostics(config_path: str = "config/config.json") -> Dict[str, Any]:
    """
    Run financial diagnostics on the data
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Dictionary with diagnostic results
    """
    try:
        # Load configuration
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Create diagnostics instance
        diagnostics = FinancialDiagnostics(config)
        
        # Run diagnostics
        results = {
            "structure": diagnostics.diagnose_data_structure(),
            "sample_facts": diagnostics.check_company_facts_sample(3),
            "metrics": diagnostics.diagnose_financial_metrics(),
            "data_folder": diagnostics.create_financial_data_folder()
        }
        
        return results
    except Exception as e:
        return {
            "error": str(e)
        }

if __name__ == "__main__":
    import argparse
    from pprint import pprint
    
    parser = argparse.ArgumentParser(description="Run financial diagnostics")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--output", help="Output file for results (JSON)")
    args = parser.parse_args()
    
    results = run_diagnostics(args.config)
    
    # Print summary
    print("\n=== Financial Data Diagnostics Summary ===")
    
    # Structure info
    dirs = results.get("structure", {}).get("directories", {})
    print("\nDirectories:")
    for path, info in dirs.items():
        status = "✅" if info.get("exists", False) else "❌"
        print(f"- {path}: {status}")
    
    # Company facts info
    facts_info = results.get("structure", {}).get("content", {}).get("company_facts", {})
    print(f"\nCompany Facts Files: {facts_info.get('file_count', 0)}")
    
    # Financial data info
    fin_data_info = results.get("structure", {}).get("content", {}).get("financial_data", {})
    print(f"Financial Data Files: {fin_data_info.get('file_count', 0)}")
    
    # Metrics info
    metrics_info = results.get("metrics", {})
    if "error" in metrics_info:
        print(f"\nFinancial Metrics Error: {metrics_info['error']}")
    else:
        print(f"\nFinancial Metrics: {metrics_info.get('row_count', 0)} companies")
        
        # Print coverage for each metric
        stats = metrics_info.get("metrics_stats", {})
        if stats:
            print("\nMetrics Coverage:")
            for metric, info in stats.items():
                if info.get("exists", False):
                    coverage = info.get("coverage", 0) * 100
                    print(f"- {metric}: {coverage:.1f}%")
                else:
                    print(f"- {metric}: Not available")
    
    # Data folder creation info
    folder_info = results.get("data_folder", {})
    if folder_info.get("success", False):
        print("\nFinancial data folder structure created successfully")
    elif "error" in folder_info:
        print(f"\nError creating financial data folder: {folder_info['error']}")
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed diagnostics saved to {args.output}")

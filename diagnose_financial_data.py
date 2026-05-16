#!/usr/bin/env python3
"""
Diagnose Financial Data

A utility script for diagnosing and fixing financial data issues
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pprint import pprint

# Add project root path to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.financial_diagnostics import run_diagnostics
from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("diagnose_financial")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Diagnose financial data issues")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--fix", action="store_true", help="Try to fix common issues")
    parser.add_argument("--detailed", action="store_true", help="Show detailed analysis")
    parser.add_argument("--output", help="Save diagnostics to JSON file")
    args = parser.parse_args()
    
    print("Running financial data diagnostics...")
    
    # Run diagnostics
    results = run_diagnostics(args.config)
    
    # Show basic summary
    dirs = results.get("structure", {}).get("directories", {})
    print("\n=== Directory Status ===")
    for path, info in dirs.items():
        status = "✅" if info.get("exists", False) else "❌"
        print(f"- {path}: {status}")
    
    # Facts files info
    facts_info = results.get("structure", {}).get("content", {}).get("company_facts", {})
    file_count = facts_info.get("file_count", 0)
    print(f"\n=== Company Facts Files: {file_count} ===")
    
    # Financial data files info
    fin_data_info = results.get("structure", {}).get("content", {}).get("financial_data", {})
    file_count = fin_data_info.get("file_count", 0)
    print(f"\n=== Financial Data Files: {file_count} ===")
    
    # Check if we created the structure
    folder_info = results.get("data_folder", {})
    if folder_info.get("success", False):
        print("\n✅ Created financial data folder structure")
    
    # If financial metrics have issues
    metrics_info = results.get("metrics", {})
    if "error" in metrics_info:
        print(f"\n⚠️ Financial Metrics Error: {metrics_info['error']}")
        
        if args.fix:
            print("\nTrying to fix financial metrics...")
            # This would implement fixes based on diagnostic results
            print("To fix metrics, run: python -m src.parsers.facts_parser")
    else:
        # Show metrics summary
        row_count = metrics_info.get("row_count", 0)
        print(f"\n=== Financial Metrics: {row_count} companies ===")
        
        # Print coverage for some key metrics
        stats = metrics_info.get("metrics_stats", {})
        if stats:
            for metric in ['quarterly_eps_growth', 'revenue_growth', 'roe']:
                info = stats.get(metric, {})
                if info.get("exists", False):
                    coverage = info.get("coverage", 0) * 100
                    count = info.get("non_null_count", 0)
                    print(f"- {metric}: {count} companies ({coverage:.1f}%)")
                else:
                    print(f"- {metric}: Not available")
    
    # Show detailed information if requested
    if args.detailed:
        print("\n=== Detailed Analysis ===")
        
        # Sample from company facts files
        sample_facts = results.get("sample_facts", {})
        if not isinstance(sample_facts, dict) or "error" in sample_facts:
            print("\nCould not analyze company facts files")
        else:
            print("\nSample Company Facts Analysis:")
            for cik, info in sample_facts.items():
                if "error" in info:
                    continue
                    
                print(f"\n- CIK: {cik}")
                print(f"  Name: {info.get('name', 'N/A')}")
                print(f"  Ticker: {info.get('ticker', 'N/A')}")
                
                # Key fields availability
                key_fields = info.get("key_fields", {})
                print(f"  Has EPS data: {'✅' if key_fields.get('has_eps', False) else '❌'}")
                print(f"  Has Revenue data: {'✅' if key_fields.get('has_revenue', False) else '❌'}")
                print(f"  Has Assets data: {'✅' if key_fields.get('has_assets', False) else '❌'}")
                print(f"  Has Equity data: {'✅' if key_fields.get('has_equity', False) else '❌'}")
                
                # Sample GAAP tags
                tags = info.get("us_gaap_tags", [])
                if tags:
                    print(f"  Sample GAAP tags: {', '.join(tags[:5])}...")
    
    # Save to file if requested
    if args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"{args.output}_{timestamp}.json" if not args.output.endswith(".json") else args.output
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed diagnostics saved to {output_file}")
    
    # Final summary with instructions
    print("\n=== Summary ===")
    if file_count == 0:
        print("⚠️ No financial data files found. This folder should contain processed financial data.")
        print("   Created placeholder folder structure in data/raw/financial_data")
        print("   You need to run the financials collection process:")
        print("   $ python -m src.growth_stock_screener --mode financials --config config/config.json")
    else:
        print(f"✅ Found {file_count} financial data files")
    
    # Always suggest running the parse mode to recalculate metrics
    print("\nTo recalculate financial metrics, run:")
    print("$ python -m src.growth_stock_screener --mode parse --config config/config.json")

if __name__ == "__main__":
    main()

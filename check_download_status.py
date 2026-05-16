#!/usr/bin/env python3
"""
Check Download Status

Script to verify if data download and parsing were successful
"""

import os
import sys
import json
import glob
import argparse

def check_download_status(config_path):
    """Check status of downloaded and parsed files"""
    # Load configuration
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        return False
        
    # Get data paths
    data_paths = config.get("data_paths", {})
    raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
    processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
    company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
    
    # Check directory existence
    dirs_to_check = [
        ("Raw data directory", raw_data_dir),
        ("Processed data directory", processed_data_dir),
        ("Company facts directory", company_facts_dir)
    ]
    
    print("Checking directory structure...")
    for name, path in dirs_to_check:
        exists = os.path.exists(path)
        status = "✅ Exists" if exists else "❌ Missing"
        print(f"- {name}: {status} ({path})")
    
    # Check for download completion markers and key files
    print("\nChecking for key files...")
    
    # Companies list file
    companies_list_file = os.path.join(processed_data_dir, "companies_list.json")
    file_exists = os.path.exists(companies_list_file)
    status = "✅ Exists" if file_exists else "❌ Missing"
    print(f"- Companies list: {status} ({companies_list_file})")
    
    # Downloaded company facts files
    company_facts_files = glob.glob(os.path.join(company_facts_dir, "CIK*.json"))
    count = len(company_facts_files)
    status = "✅" if count > 0 else "❌"
    print(f"- Company facts files: {status} ({count} files)")
    
    # Parsed financial metrics
    metrics_file = os.path.join(processed_data_dir, "financial_metrics.parquet")
    file_exists = os.path.exists(metrics_file)
    status = "✅ Exists" if file_exists else "❌ Missing"
    print(f"- Financial metrics: {status} ({metrics_file})")
    
    # Results file
    results_file = data_paths.get("output_file", os.path.join(processed_data_dir, "results.csv"))
    file_exists = os.path.exists(results_file)
    status = "✅ Exists" if file_exists else "❌ Missing"
    print(f"- Results file: {status} ({results_file})")
    
    # Print next steps based on findings
    print("\nRecommendations:")
    
    if not os.path.exists(companies_list_file) or len(company_facts_files) == 0:
        print("- Download data is missing or incomplete. Run the download mode:")
        print("  python growth_stock_screener.py --mode download")
        
    if os.path.exists(companies_list_file) and len(company_facts_files) > 0 and not os.path.exists(metrics_file):
        print("- Company data exists but financial metrics are missing. Run the parse mode:")
        print("  python growth_stock_screener.py --mode parse")
        
    if os.path.exists(metrics_file) and not os.path.exists(results_file):
        print("- Financial metrics exist but results are missing. Run the screen mode:")
        print("  python growth_stock_screener.py --mode screen")

    # Check permissions if files exists but might be empty
    if file_exists and os.path.getsize(metrics_file) == 0:
        print("⚠️ Financial metrics file exists but is empty!")
        
    if file_exists and os.path.getsize(companies_list_file) == 0:
        print("⚠️ Companies list file exists but is empty!")

    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check status of data download and parsing")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    args = parser.parse_args()
    
    check_download_status(args.config)

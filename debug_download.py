#!/usr/bin/env python3
"""
Debug Download Script

Download data for a single company to test the download process
"""

import os
import sys
import json
import argparse

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.api.sec_client import SECClient
from src.collectors.facts_collector import CompanyFactsCollector
from src.utils.logger import setup_logger
from src.utils.directory import ensure_directories

# Setup logger
logger = setup_logger("debug_download")

def download_single_company(config_path, cik):
    """Download data for a single company"""
    print(f"Downloading data for CIK: {cik}")
    
    # Load configuration
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return False
    
    # Ensure directories exist
    ensure_directories(config)
    
    # Initialize SEC API client
    user_agent = config.get("sec_api", {}).get("user_agent")
    if not user_agent:
        logger.error("User-Agent not provided in config file")
        return False
    
    rate_limit = config.get("sec_api", {}).get("rate_limit_delay", 0.1)
    sec_client = SECClient(user_agent=user_agent, rate_limit_delay=rate_limit)
    
    # Initialize facts collector
    facts_collector = CompanyFactsCollector(sec_client, config)
    
    # Create output directory manually to ensure it exists
    data_paths = config.get("data_paths", {})
    company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
    temp_dir = os.path.join(company_facts_dir, "temp")
    
    os.makedirs(company_facts_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    print(f"Company facts directory: {company_facts_dir} (exists: {os.path.exists(company_facts_dir)})")
    print(f"Temp directory: {temp_dir} (exists: {os.path.exists(temp_dir)})")
    
    # Download company facts
    result = facts_collector.download_company_facts(cik)
    
    # Check result
    if result:
        output_file = result
        print(f"✅ Successfully downloaded data to: {output_file}")
        print(f"File size: {os.path.getsize(output_file)} bytes")
        
        # Show file sample
        try:
            with open(output_file, 'r') as f:
                data = json.load(f)
            print("\nFile sample:")
            print(f"Company name: {data.get('entityName', 'N/A')}")
            print(f"CIK: {data.get('cik', 'N/A')}")
            us_gaap = data.get('facts', {}).get('us-gaap', {})
            print(f"Number of us-gaap facts: {len(us_gaap)}")
            if us_gaap:
                print("Sample tags:", list(us_gaap.keys())[:5])
        except Exception as e:
            print(f"Error reading file: {e}")
    else:
        print(f"❌ Failed to download data for CIK: {cik}")
    
    return bool(result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug download for a single company")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--cik", required=True, help="Company CIK number")
    args = parser.parse_args()
    
    success = download_single_company(args.config, args.cik)
    sys.exit(0 if success else 1)

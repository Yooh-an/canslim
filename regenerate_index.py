#!/usr/bin/env python3
"""
Regenerate company index from submissions data.
"""

import os
import sys
import json

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.parsers.submissions_parser import SubmissionsParser
from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("regenerate_index")

def main():
    """Main function to regenerate company index."""
    # Load configuration
    config_path = os.path.join("config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return
    
    # Get index file path for potential deletion
    data_paths = config.get("data_paths", {})
    processed_dir = data_paths.get("processed_data_dir", "data/processed")
    index_file = os.path.join(processed_dir, "companies_index.parquet")
    
    # Delete existing index if it exists
    if os.path.exists(index_file):
        logger.info(f"Removing existing index file: {index_file}")
        os.remove(index_file)
    else:
        logger.info(f"No existing index file found at: {index_file}")
    
    # Create SubmissionsParser and regenerate index
    logger.info("Regenerating company index...")
    parser = SubmissionsParser(config)
    df = parser.create_company_index(force=True)
    
    logger.info(f"Successfully regenerated index with {len(df)} companies")
    
    # Print first few companies for verification
    if not df.empty:
        logger.info("\nSample companies:")
        for idx, row in df.head(5).iterrows():
            logger.info(f"CIK: {row['cik']}, Ticker: {row['ticker']}, Name: {row['name']}")

if __name__ == "__main__":
    main()

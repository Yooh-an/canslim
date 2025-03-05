"""
Directory management utilities for the Growth Stock Screener.
"""

import os
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("directory_utils")

def ensure_directories(config):
    """
    Ensure that all required directories exist.
    
    Args:
        config: The application configuration dictionary
    """
    # Extract directory paths from config
    raw_data_dir = config.get("data_paths", {}).get("raw_data_dir", "data/raw")
    processed_data_dir = config.get("data_paths", {}).get("processed_data_dir", "data/processed")
    company_facts_dir = config.get("data_paths", {}).get("company_facts_dir", "data/raw/company_facts")
    log_dir = os.path.dirname(config.get("logging", {}).get("log_file", "logs/screener.log"))
    
    # Create directories
    directories = [
        raw_data_dir,
        processed_data_dir,
        company_facts_dir,
        log_dir,
        "config"
    ]
    
    for directory in directories:
        if directory:  # Skip empty strings
            Path(directory).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory ensured: {directory}")
    
    logger.info("All required directories have been created.")

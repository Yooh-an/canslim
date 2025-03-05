"""
Directory utility functions.
"""

import os
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("directory_utils")

def ensure_directories(config):
    """
    Ensure all necessary directories specified in config exist.
    
    Args:
        config: Application configuration dictionary
    """
    # Create data directories
    data_paths = config.get("data_paths", {})
    dirs_to_create = [
        data_paths.get("raw_data_dir", "data/raw"),
        data_paths.get("processed_data_dir", "data/processed"),
        data_paths.get("company_facts_dir", "data/raw/company_facts"),
        os.path.dirname(data_paths.get("output_file", "data/processed/results.csv")),
    ]
    
    # Create log directory
    log_file = config.get("logging", {}).get("log_file", "logs/screener.log")
    if log_file:
        dirs_to_create.append(os.path.dirname(log_file))
    
    # Create all directories
    for directory in dirs_to_create:
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory ensured: {directory}")
    
    logger.info("All required directories have been created.")

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
    data_paths = config.get("data_paths", {})
    
    # List of required directories with user-friendly names
    required_dirs = [
        ("raw_data_dir", data_paths.get("raw_data_dir", "data/raw")),
        ("processed_data_dir", data_paths.get("processed_data_dir", "data/processed")),
        ("company_facts_dir", data_paths.get("company_facts_dir", "data/raw/company_facts")),
        ("financial_data_dir", os.path.join(data_paths.get("raw_data_dir", "data/raw"), "financial_data"))
    ]
    
    # Check each directory
    missing_dirs = []
    for name, path in required_dirs:
        if not os.path.exists(path):
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created directory: {path}")
            except Exception as e:
                missing_dirs.append((name, path, str(e)))
    
    # Report any issues
    if missing_dirs:
        logger.warning("The following directories could not be created:")
        for name, path, error in missing_dirs:
            logger.warning(f"- {name}: {path} (Error: {error})")
        return False
        
    return True

def check_file_permissions(file_path):
    """Check if a file has proper read/write permissions"""
    if not os.path.exists(file_path):
        return False, "File does not exist"
        
    readable = os.access(file_path, os.R_OK)
    writable = os.access(file_path, os.W_OK)
    
    if readable and writable:
        return True, "File has proper permissions"
    elif readable:
        return False, "File is readable but not writable"
    elif writable:
        return False, "File is writable but not readable"
    else:
        return False, "File is neither readable nor writable"

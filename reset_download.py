#!/usr/bin/env python3
"""
Reset download script to clean up and start fresh.

This script deletes all downloaded and processed data to reset the application
to a clean state for a fresh start.
"""

import os
import shutil
import argparse
import json
from pathlib import Path

def reset_download(config_file="config/config.json", keep_submissions=False):
    """
    Reset the application by deleting downloaded and processed data.
    
    Args:
        config_file: Path to config file
        keep_submissions: If True, keep the submissions.zip file
    """
    print("Resetting Growth Stock Screener data...")
    
    # Load config
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config file: {e}")
        return
    
    # Get data paths
    data_paths = config.get("data_paths", {})
    raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
    processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
    submissions_file = data_paths.get("submissions_file", "data/raw/submissions.zip")
    company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
    
    # Clean up raw data
    if os.path.exists(raw_data_dir):
        # If keeping submissions, move it to temp location
        if keep_submissions and os.path.exists(submissions_file):
            print(f"Keeping submissions file: {submissions_file}")
            temp_file = submissions_file + ".temp"
            shutil.move(submissions_file, temp_file)
        
        # Delete raw directory contents
        print(f"Deleting raw data directory: {raw_data_dir}")
        shutil.rmtree(raw_data_dir, ignore_errors=True)
        
        # Recreate directories
        Path(raw_data_dir).mkdir(parents=True, exist_ok=True)
        
        # Move submissions file back if needed
        if keep_submissions and os.path.exists(temp_file):
            Path(os.path.dirname(submissions_file)).mkdir(parents=True, exist_ok=True)
            shutil.move(temp_file, submissions_file)
            print(f"Restored submissions file: {submissions_file}")
    
    # Clean up processed data
    if os.path.exists(processed_data_dir):
        print(f"Deleting processed data directory: {processed_data_dir}")
        shutil.rmtree(processed_data_dir, ignore_errors=True)
        Path(processed_data_dir).mkdir(parents=True, exist_ok=True)
    
    print("Reset complete. The application is ready for a fresh start.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset Growth Stock Screener data")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    parser.add_argument("--keep-submissions", action="store_true", 
                       help="Keep the submissions.zip file to avoid re-downloading")
    
    args = parser.parse_args()
    reset_download(args.config, args.keep_submissions)

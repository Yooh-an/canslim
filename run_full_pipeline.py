#!/usr/bin/env python3
"""
Full Pipeline Runner Script

This script runs the entire growth stock screening pipeline from data download
through screening in a single command.
"""

import os
import sys
import argparse
import subprocess
import time
from datetime import datetime
import json

def run_command(command, description=None):
    """Run a command and print its output"""
    if description:
        print(f"\n{'='*20} {description} {'='*20}")
    
    print(f"Running: {command}")
    start_time = time.time()
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Command completed in {duration:.2f} seconds")
    print(f"Exit code: {result.returncode}")
    
    # Print stdout and stderr
    if result.stdout:
        print("\nOutput:")
        print(result.stdout)
    
    if result.stderr:
        print("\nErrors:")
        print(result.stderr)
    
    return result.returncode == 0

def main():
    """Main function to run the full pipeline"""
    parser = argparse.ArgumentParser(description='Run the full growth stock screening pipeline')
    parser.add_argument('--config', default='config/config.json', help='Path to config file')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], 
                      help='Logging level')
    parser.add_argument('--skip-download', action='store_true', help='Skip data download step')
    parser.add_argument('--skip-parse', action='store_true', help='Skip data parsing step')
    parser.add_argument('--skip-enrich', action='store_true', help='Skip data enrichment step')
    parser.add_argument('--force', action='store_true', help='Force reprocessing of all steps')
    
    args = parser.parse_args()
    
    print(f"Growth Stock Screening Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Configuration: {args.config}")
    
    # Instead of passing force as a command line argument, set it in the config
    config = load_config(args.config)
    if args.force:
        # Modify the config to force reprocessing
        if "download_settings" not in config:
            config["download_settings"] = {}
        config["download_settings"]["force_download"] = True
        
        # Write the updated config to a temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            temp_config_path = temp_file.name
            json.dump(config, temp_file, indent=2)
    else:
        temp_config_path = args.config
    
    success = True
    
    # Create the base command using the temporary config
    base_cmd = f"python run_screener.py --config {temp_config_path} --log-level {args.log_level}"
    
    # Step 1: Download data
    if not args.skip_download:
        success = run_command(
            f"{base_cmd} --mode download",
            "DOWNLOADING DATA"
        )
        
        if not success:
            print("Error: Download step failed. Exiting.")
            if args.force and os.path.exists(temp_config_path):
                os.unlink(temp_config_path)
            sys.exit(1)
    
    # Verify download by checking financial data
    run_command("python check_financial_data.py", "CHECKING FINANCIAL DATA")
    
    # Step 2: Parse data
    if not args.skip_parse:
        success = run_command(
            f"{base_cmd} --mode parse",
            "PARSING DATA"
        )
        
        if not success:
            print("Error: Parse step failed. Exiting.")
            if args.force and os.path.exists(temp_config_path):
                os.unlink(temp_config_path)
            sys.exit(1)
    
    # Verify parsing by checking metrics
    run_command("python check_metrics.py", "CHECKING METRICS")
    
    # Step 3: Enrich data
    if not args.skip_enrich:
        success = run_command(
            f"{base_cmd} --mode enrich",
            "ENRICHING DATA"
        )
        
        if not success:
            print("Warning: Enrichment step failed. Continuing with limited data.")
    
    # Step 4: Screen stocks
    success = run_command(
        f"{base_cmd} --mode screen",
        "SCREENING STOCKS"
    )
    
    # Clean up temporary config file
    if args.force and os.path.exists(temp_config_path):
        os.unlink(temp_config_path)
    
    if success:
        print("\n=== Pipeline completed successfully! ===")
        print("\nResults are available in the file specified in your config.")
        print("To view detailed results, open the CSV file in Excel or another spreadsheet program.")
    else:
        print("\n=== Pipeline completed with errors ===")
        print("Please check the logs for more information.")
        sys.exit(1)

def load_config(config_path="config/config.json"):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

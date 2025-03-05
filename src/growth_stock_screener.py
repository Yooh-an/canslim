#!/usr/bin/env python3
"""
Growth Stock Screener

A command-line tool for screening growth stocks using SEC EDGAR data.
"""

import argparse
import json
import os
import sys
import logging
from pathlib import Path

from utils.logger import setup_logger
from utils.directory import ensure_directories

def load_config(config_path):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"Config file '{config_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error(f"Config file '{config_path}' is not valid JSON.")
        sys.exit(1)

def download_data(config):
    """Download data from SEC EDGAR."""
    logger.info("Downloading data from SEC EDGAR...")
    # This will be implemented in Phase 2
    pass

def parse_data(config):
    """Parse downloaded data and calculate metrics."""
    logger.info("Parsing data and calculating metrics...")
    # This will be implemented in Phase 3
    pass

def screen_stocks(config):
    """Screen stocks based on criteria."""
    logger.info("Screening stocks based on criteria...")
    # This will be implemented in Phase 4
    pass

def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - Find high-growth stocks using SEC EDGAR data."
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=["download", "parse", "screen"],
        help="Operation mode: download SEC data, parse data, or screen stocks"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (default: config/config.json)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Setup logging
    log_file = config.get("logging", {}).get("log_file", "logs/screener.log")
    log_level = getattr(logging, args.log_level)
    
    global logger
    logger = setup_logger("growth_stock_screener", log_file, log_level)
    
    logger.debug("Configuration loaded successfully.")
    
    # Ensure required directories exist
    ensure_directories(config)
    
    # Execute requested mode
    if args.mode == "download":
        download_data(config)
    elif args.mode == "parse":
        parse_data(config)
    elif args.mode == "screen":
        screen_stocks(config)

if __name__ == "__main__":
    import logging
    main()

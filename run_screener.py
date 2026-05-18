#!/usr/bin/env python3
"""
Growth Stock Screener Runner Script

This script resolves Python path issues.
"""

import os
import sys
import argparse

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def main():
    """Parse command line arguments and run the main screener."""
    parser = argparse.ArgumentParser(
        description="Growth Stock Screener - A tool for screening growth stocks using SEC EDGAR data"
    )
    
    parser.add_argument(
        "--mode",
        required=True,
        choices=["download", "parse", "enrich", "leadership", "financials", "screen", "status", "update", "analyze", "tv-export"],
        help="Operation mode: download SEC data, parse data, enrich data, screen stocks, export TradingView artifacts, inspect status, or update missing stages"
    )
    
    parser.add_argument(
        "--config",
        default=os.path.join("config", "config.json"),
        help="Path to configuration file (default: config/config.json)"
    )

    parser.add_argument(
        "--profile",
        help="Optional screener profile name under config/profiles, e.g. canslim_pure"
    )

    parser.add_argument(
        "--ticker",
        help="Ticker to analyze when --mode analyze is used"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Run main screener
    from src.growth_stock_screener import main as run_screener
    
    # Pass arguments correctly
    sys.argv = [sys.argv[0], "--mode", args.mode, "--config", args.config, "--log-level", args.log_level]
    if args.profile:
        sys.argv.extend(["--profile", args.profile])
    if args.ticker:
        sys.argv.extend(["--ticker", args.ticker])
    run_screener()

if __name__ == "__main__":
    main()

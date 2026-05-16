#!/usr/bin/env python3
"""
Growth Stock Screener Data Validation Script

Script to verify the validity and completeness of downloaded company data files
"""

import os
import sys
import argparse
import json

# Add project root path to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.utils.data_validator import validate_data
from src.utils.report_generator import ReportGenerator
from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("validate_data")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Growth Stock Screener Data Validation")
    parser.add_argument("--config", default="config/config.json", help="Configuration file path")
    parser.add_argument("--report", action="store_true", help="Generate and save report")
    parser.add_argument("--output-dir", default="reports", help="Report output directory")
    args = parser.parse_args()
    
    logger.info(f"Configuration file: {args.config}")
    
    try:
        # Execute data validation
        results = validate_data(args.config)
        
        # Output to console by default
        report_generator = ReportGenerator(results)
        report_text = report_generator.generate_text_report()
        print(report_text)
        
        # Save to file if option is specified
        if args.report:
            report_file = report_generator.save_report(args.output_dir)
            logger.info(f"Report saved to: {report_file}")
        
        # Determine exit code
        overall_status = results.get("overall", {}).get("status")
        if overall_status == "FAIL":
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"Error during validation: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()

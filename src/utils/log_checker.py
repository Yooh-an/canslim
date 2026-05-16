"""
Utility script to check log files for errors and warnings
"""
import os
import re
import argparse
from datetime import datetime

def parse_log_file(log_file_path):
    """Parse log file and extract errors and warnings"""
    if not os.path.exists(log_file_path):
        print(f"Log file not found: {log_file_path}")
        return [], []
        
    errors = []
    warnings = []
    
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if 'ERROR' in line:
                errors.append(line.strip())
            elif 'WARNING' in line:
                warnings.append(line.strip())
                
    return errors, warnings

def print_log_summary(log_file_path):
    """Print summary of errors and warnings in log file"""
    errors, warnings = parse_log_file(log_file_path)
    
    print(f"\n=== Log Analysis: {log_file_path} ===")
    print(f"Found {len(errors)} errors and {len(warnings)} warnings\n")
    
    if errors:
        print("== ERRORS ==")
        for i, error in enumerate(errors[-10:], 1):  # Show last 10 errors
            print(f"{i}. {error}")
        if len(errors) > 10:
            print(f"... and {len(errors) - 10} more errors\n")
            
    if warnings:
        print("\n== WARNINGS ==")
        for i, warning in enumerate(warnings[-10:], 1):  # Show last 10 warnings
            print(f"{i}. {warning}")
        if len(warnings) > 10:
            print(f"... and {len(warnings) - 10} more warnings\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check log files for errors and warnings")
    parser.add_argument("--log-file", default="logs/screener.log", help="Path to log file")
    args = parser.parse_args()
    
    print_log_summary(args.log_file)

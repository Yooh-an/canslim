#!/usr/bin/env python3
"""
Analyze SEC EDGAR file structure to understand the format.
"""

import os
import json
import glob
from collections import Counter

def analyze_json_structure(directory_path):
    """Analyze the structure of JSON files in the directory."""
    print(f"Analyzing JSON files in {directory_path}")
    
    # Find all JSON files
    json_files = glob.glob(os.path.join(directory_path, "**/*.json"), recursive=True)
    print(f"Found {len(json_files)} JSON files")
    
    if not json_files:
        print("No JSON files found to analyze.")
        return
    
    # Sample some files
    sample_size = min(50, len(json_files))
    print(f"Analyzing a sample of {sample_size} files...")
    
    # Collect structure info
    structure_types = Counter()
    top_level_keys = Counter()
    cik_files = []
    ticker_files = []
    
    for file_path in json_files[:sample_size]:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Check structure type
            if isinstance(data, dict):
                structure_types["dict"] += 1
                
                # Collect top-level keys
                for key in data.keys():
                    top_level_keys[key] += 1
                
                # Check for company identifiers
                if "cik" in data:
                    cik_files.append(file_path)
                if "tickers" in data:
                    ticker_files.append(file_path)
                    
            elif isinstance(data, list):
                structure_types["list"] += 1
            else:
                structure_types[str(type(data))] += 1
                
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
    
    # Print results
    print("\nStructure Types:")
    for struct_type, count in structure_types.items():
        print(f"  {struct_type}: {count} files")
    
    print("\nTop-level Keys (from dict files):")
    for key, count in top_level_keys.most_common(20):
        print(f"  {key}: {count} files")
    
    print(f"\nFound {len(cik_files)} files with 'cik' key")
    if cik_files:
        print("Sample CIK files:")
        for file_path in cik_files[:3]:
            print(f"  {file_path}")
    
    print(f"\nFound {len(ticker_files)} files with 'tickers' key")
    if ticker_files:
        print("Sample ticker files:")
        for file_path in ticker_files[:3]:
            print(f"  {file_path}")
            # Print sample ticker file content
            if ticker_files:
                print("\nSample content from ticker file:")
                with open(ticker_files[0], 'r') as f:
                    ticker_data = json.load(f)
                print(json.dumps(ticker_data, indent=2)[:1000] + "...\n")

if __name__ == "__main__":
    submissions_dir = "data/raw/submissions_extracted"
    analyze_json_structure(submissions_dir)

#!/usr/bin/env python3
"""
Deep analysis of SEC EDGAR company facts files.
"""

import os
import json
import glob
from collections import Counter
import re

def analyze_company_facts(directory_path, sample_size=10):
    """Analyze the structure of company facts files to find ticker symbols."""
    print(f"Deep analyzing company facts files in {directory_path}")
    
    # Find all JSON files
    json_files = glob.glob(os.path.join(directory_path, "**/*.json"), recursive=True)
    print(f"Found {len(json_files)} JSON files")
    
    if not json_files:
        print("No JSON files found to analyze.")
        return
    
    # Sample some files
    sample_files = json_files[:sample_size]
    print(f"Analyzing a sample of {len(sample_files)} files...")
    
    for file_path in sample_files:
        print(f"\nAnalyzing file: {os.path.basename(file_path)}")
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            print(f"CIK: {data.get('cik')}")
            print(f"Entity Name: {data.get('entityName')}")
            
            # Look for possible ticker information in the facts section
            if 'facts' in data:
                # Look for specific concepts that might contain ticker info
                facts = data['facts']
                
                print("Examining facts section:")
                # Look at top-level taxonomies
                print(f"Taxonomies: {list(facts.keys())}")
                
                # Look for dei namespace which often contains company info
                if 'dei' in facts:
                    print("\nFound 'dei' taxonomy - examining contents:")
                    dei_concepts = facts['dei'].keys()
                    ticker_related = [concept for concept in dei_concepts 
                                    if 'ticker' in concept.lower() or 'symbol' in concept.lower() 
                                    or 'trade' in concept.lower()]
                    
                    if ticker_related:
                        print(f"Possible ticker-related concepts: {ticker_related}")
                        
                        # Print values of these concepts
                        for concept in ticker_related:
                            if concept in facts['dei']:
                                units = facts['dei'][concept].get('units', {})
                                if units:
                                    unit_type = list(units.keys())[0]  # Get first unit type
                                    values = units[unit_type]
                                    print(f"\nConcept: {concept}")
                                    print(f"Values: {values[:2]}")  # Just print first couple
                
                # Check if entityInformation might be present
                possible_entity_info = [k for k in facts.keys() if 'entity' in k.lower()]
                if possible_entity_info:
                    print(f"\nPossible entity information taxonomies: {possible_entity_info}")
                
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")

def look_for_alternative_ticker_sources(directory_path):
    """Look for any other files or patterns that might contain ticker info."""
    print("\nLooking for alternative ticker sources...")
    
    # Check for any README or index files
    index_files = glob.glob(os.path.join(directory_path, "**/index.*"), recursive=True)
    index_files.extend(glob.glob(os.path.join(directory_path, "**/README.*"), recursive=True))
    
    if index_files:
        print(f"Found {len(index_files)} possible index files:")
        for file in index_files:
            print(f"  - {file}")
    
    # Check if CIK numbers might map to tickers in file names
    file_patterns = Counter()
    for file in os.listdir(directory_path):
        if os.path.isfile(os.path.join(directory_path, file)):
            # Extract file pattern by replacing digits with #
            pattern = re.sub(r'\d', '#', file)
            file_patterns[pattern] += 1
    
    print("\nFile name patterns:")
    for pattern, count in file_patterns.most_common():
        print(f"  {pattern}: {count} files")

if __name__ == "__main__":
    submissions_dir = "data/raw/submissions_extracted"
    analyze_company_facts(submissions_dir)
    look_for_alternative_ticker_sources(submissions_dir)

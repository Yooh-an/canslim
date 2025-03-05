"""
XBRL Facts Parser

Module for parsing SEC XBRL company facts data and extracting financial metrics.
"""

import os
import json
import glob
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Set, Union

# Import logger from src.utils instead of utils
try:
    from src.utils.logger import setup_logger
except ImportError:
    # Fallback import for when running from the module directly
    from utils.logger import setup_logger

# Set up logger
logger = setup_logger("facts_parser")

class XBRLFactsParser:
    """
    Parser for SEC XBRL company facts data.
    
    This class extracts key financial metrics from company facts files,
    handling different taxonomy variations and data structures.
    """
    
    # Common tag variations for key metrics
    # Each set contains possible XBRL tags for the same concept
    TAG_VARIATIONS = {
        'eps': {
            'us-gaap:EarningsPerShareDiluted',
            'us-gaap:EarningsPerShareBasicAndDiluted',
            'us-gaap:EarningsPerShareBasic',
            'us-gaap:IncomeLossPerShareBasicAndDiluted'
        },
        'revenue': {
            'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
            'us-gaap:Revenues',
            'us-gaap:SalesRevenueNet',
            'us-gaap:RevenueNet',
            'us-gaap:Revenue'
        },
        'net_income': {
            'us-gaap:NetIncomeLoss',
            'us-gaap:ProfitLoss', 
            'us-gaap:NetIncome'
        },
        'assets': {
            'us-gaap:Assets',
            'us-gaap:AssetsCurrent'
        },
        'liabilities': {
            'us-gaap:Liabilities',
            'us-gaap:LiabilitiesCurrent'
        },
        'equity': {
            'us-gaap:StockholdersEquity',
            'us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
            'us-gaap:LiabilitiesAndStockholdersEquity'
        }
    }
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the XBRLFactsParser."""
        self.config = config
        
        # Get data paths from config
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        
        # Define output paths
        self.parsed_metrics_file = os.path.join(self.processed_data_dir, "financial_metrics.parquet")
        
        # Ensure directories exist
        Path(self.processed_data_dir).mkdir(parents=True, exist_ok=True)
    
    def get_company_facts_files(self) -> List[str]:
        """
        Get a list of all company facts files in the facts directory.
        
        Returns:
            List of file paths
        """
        files = glob.glob(os.path.join(self.company_facts_dir, "CIK*.json"))
        logger.info(f"Found {len(files)} company facts files")
        return files
    
    def load_company_facts(self, file_path: str) -> Dict[str, Any]:
        """
        Load company facts data from a file.
        
        Args:
            file_path: Path to the company facts JSON file
            
        Returns:
            Dictionary containing the company facts data
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"Error loading company facts from {file_path}: {e}")
            return {}
    
    def find_best_tag(self, concept: str, facts: Dict[str, Any]) -> Optional[str]:
        """Find the best available tag for a given concept."""
        if concept not in self.TAG_VARIATIONS:
            logger.warning(f"Unknown concept: {concept}")
            return None
        
        # Look for exact matches in the variation set
        tag_variations = self.TAG_VARIATIONS[concept]
        for tag in tag_variations:
            if tag in facts.get('facts', {}).get('us-gaap', {}):
                return tag
        
        return None
        
    def extract_quarterly_values(self, concept_data: Dict[str, Any],
                                unit_type: str = "USD") -> Dict[str, float]:
        """Extract quarterly values from concept data."""
        values = {}
        
        # Check if the unit type exists
        units = concept_data.get('units', {})
        unit_values = units.get(unit_type)
        
        if not unit_values:
            return values
        
        for item in unit_values:
            # Filter to quarterly (form 10-Q) reports only
            if 'form' not in item or item['form'] != '10-Q':
                continue
                
            # Make sure we have a proper period
            if 'period' not in item or 'endDate' not in item['period']:
                continue
            
            end_date = item['period']['endDate']
            
            # Store the value with the end date
            values[end_date] = float(item['val'])
        
        return values
    
    def process_all(self, limit: Optional[int] = None, force: bool = False) -> pd.DataFrame:
        """
        Process all company facts files and generate metrics.
        
        Args:
            limit: Optional limit on number of companies to process
            force: If True, reprocess even if output file exists
            
        Returns:
            DataFrame containing processed metrics
        """
        # Basic implementation
        metrics = []
        
        # Get company facts files (limited if specified)
        files = self.get_company_facts_files()
        if limit and limit < len(files):
            files = files[:limit]
        
        # Process each file
        for file_path in files:
            try:
                # Extract CIK from filename
                cik = os.path.basename(file_path).replace('CIK', '').replace('.json', '')
                
                # Load facts
                facts = self.load_company_facts(file_path)
                if not facts:
                    continue
                
                # Create metrics entry
                metrics.append({
                    'cik': cik,
                    'name': facts.get('entityName', ''),
                    'ticker': facts.get('tickers', [''])[0] if facts.get('tickers') else ''
                })
                
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
        
        # Convert to DataFrame
        df = pd.DataFrame(metrics)
        
        # Save to parquet file
        if not df.empty:
            df.to_parquet(self.parsed_metrics_file, index=False)
        
        return df

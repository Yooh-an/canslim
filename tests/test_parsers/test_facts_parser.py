"""
Unit tests for XBRLFactsParser.
"""

import os
import unittest
import tempfile
import json
import pandas as pd
import numpy as np
from unittest.mock import patch, Mock, MagicMock
import shutil
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Import XBRLFactsParser from src.parsers.facts_parser
from src.parsers.facts_parser import XBRLFactsParser

class TestXBRLFactsParser(unittest.TestCase):
    """Test cases for the XBRLFactsParser class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temp directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
        # Create config with temp paths
        self.config = {
            "data_paths": {
                "raw_data_dir": os.path.join(self.temp_dir, "raw"),
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
                "company_facts_dir": os.path.join(self.temp_dir, "raw/company_facts"),
            }
        }
        
        # Create parser
        self.parser = XBRLFactsParser(self.config)
        
        # Create directory structure
        os.makedirs(self.config["data_paths"]["raw_data_dir"], exist_ok=True)
        os.makedirs(self.config["data_paths"]["processed_data_dir"], exist_ok=True)
        os.makedirs(self.config["data_paths"]["company_facts_dir"], exist_ok=True)
    
    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test that parser initializes with correct parameters."""
        print("Running facts parser test_initialization")
        self.assertEqual(self.parser.raw_data_dir, os.path.join(self.temp_dir, "raw"))
        self.assertEqual(self.parser.processed_data_dir, os.path.join(self.temp_dir, "processed"))
        self.assertTrue(os.path.isdir(self.parser.processed_data_dir), "Processed directory should be created")

    def test_empty_result_when_no_files(self):
        """Test that an empty DataFrame is returned when no files exist."""
        print("Running facts parser test_empty_result_when_no_files")
        result = self.parser.process_all()
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

    def test_load_company_facts(self):
        """Test loading company facts from a file."""
        print("Running facts parser test_load_company_facts")
        # Create a test facts file
        test_data = {
            "cik": "0000123456",
            "entityName": "Test Company",
            "tickers": ["TEST"]
        }
        
        file_path = os.path.join(self.config["data_paths"]["company_facts_dir"], "CIK0000123456.json")
        with open(file_path, 'w') as f:
            json.dump(test_data, f)
        
        # Load the facts
        facts = self.parser.load_company_facts(file_path)
        
        # Verify
        self.assertEqual(facts["cik"], "0000123456")
        self.assertEqual(facts["entityName"], "Test Company")
        self.assertEqual(facts["tickers"], ["TEST"])
        

if __name__ == '__main__':
    unittest.main()
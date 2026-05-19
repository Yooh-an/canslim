"""
Unit tests for SubmissionsCollector.
"""

import os
import unittest
import tempfile
import json
import zipfile
from unittest.mock import patch, Mock, MagicMock
import datetime
import shutil

from src.collectors.submissions_collector import SubmissionsCollector
from src.api.sec_client import SECClient

class TestSubmissionsCollector(unittest.TestCase):
    """Test cases for the SubmissionsCollector class."""
    
    def setUp(self):
        """Set up test environment."""
        self.user_agent = "Test User (test@example.com)"
        self.sec_client = Mock(spec=SECClient)
        
        # Create a temp directory for tests
        self.temp_dir = tempfile.mkdtemp()
        
        # Create config with temp paths
        self.config = {
            "data_paths": {
                "raw_data_dir": os.path.join(self.temp_dir, "raw"),
                "submissions_file": os.path.join(self.temp_dir, "raw/submissions.zip"),
            }
        }
        
        # Create collector
        self.collector = SubmissionsCollector(self.sec_client, self.config)
        
        # Create directory structure
        os.makedirs(os.path.join(self.temp_dir, "raw"), exist_ok=True)
        os.makedirs(self.collector.extracted_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir)
    
    def test_initialization(self):
        """Test that collector initializes with correct parameters."""
        self.assertEqual(self.collector.sec_client, self.sec_client)
        self.assertEqual(self.collector.raw_data_dir, os.path.join(self.temp_dir, "raw"))
        self.assertEqual(self.collector.submissions_file, os.path.join(self.temp_dir, "raw/submissions.zip"))
    
    def test_check_existing_file_none(self):
        """Test check_existing_file when no file exists."""
        self.assertFalse(self.collector.check_existing_file())
    
    def test_check_existing_file_old(self):
        """Test check_existing_file when file is too old."""
        # Create a file
        with open(self.collector.submissions_file, 'w') as f:
            f.write("dummy content")
        
        # Mock file time to be old
        old_time = datetime.datetime.now() - datetime.timedelta(days=30)
        os.utime(self.collector.submissions_file, (old_time.timestamp(), old_time.timestamp()))
        
        # Set max age to smaller value
        self.collector.config["max_file_age_days"] = 7
        
        self.assertFalse(self.collector.check_existing_file())
    
    def test_check_existing_file_too_small(self):
        """Test check_existing_file when file is too small."""
        # Create a small file
        with open(self.collector.submissions_file, 'w') as f:
            f.write("small")
        
        self.assertFalse(self.collector.check_existing_file())
    
    def test_check_existing_file_valid(self):
        """Test check_existing_file when file is valid."""
        # Create a file with sufficient size
        with open(self.collector.submissions_file, 'wb') as f:
            f.write(b'0' * 10 * 1024 * 1024)  # 10MB dummy data
        
        self.assertTrue(self.collector.check_existing_file())
    
    @patch('src.collectors.submissions_collector.SubmissionsCollector.check_existing_file')
    def test_download_submissions_existing(self, mock_check):
        """Test download_submissions uses existing file."""
        mock_check.return_value = True
        
        result = self.collector.download_submissions()
        
        # Should not call sec_client
        self.sec_client.download_file.assert_not_called()
        self.assertEqual(result, self.collector.submissions_file)
    
    @patch('src.collectors.submissions_collector.SubmissionsCollector.check_existing_file')
    def test_download_submissions_force(self, mock_check):
        """Test download_submissions with force=True."""
        mock_check.return_value = True
        self.sec_client.download_file.return_value = self.collector.submissions_file
        
        result = self.collector.download_submissions(force=True)
        
        # Should call sec_client even if file exists
        self.sec_client.download_file.assert_called_once()
        self.assertEqual(result, self.collector.submissions_file)
    
    @patch('src.collectors.submissions_collector.SubmissionsCollector.check_existing_file')
    def test_download_submissions_new(self, mock_check):
        """Test download_submissions for new file."""
        mock_check.return_value = False
        self.sec_client.download_file.return_value = self.collector.submissions_file
        
        result = self.collector.download_submissions()
        
        # Should call sec_client
        self.sec_client.download_file.assert_called_once()
        self.assertEqual(result, self.collector.submissions_file)
    
    def test_extract_submissions(self):
        """Test extract_submissions."""
        # Create a test zip file
        with zipfile.ZipFile(self.collector.submissions_file, 'w') as zip_f:
            zip_f.writestr('companies.json', '{"123456": {"name": "Test Company"}}')
        
        # Extract it
        result = self.collector.extract_submissions()
        
        # Check result and extraction
        self.assertEqual(result, self.collector.extracted_dir)
        self.assertTrue(os.path.exists(os.path.join(self.collector.extracted_dir, 'companies.json')))
    
    def test_extract_submissions_bad_zip(self):
        """Test extract_submissions with bad zip file."""
        # Create an invalid zip file
        with open(self.collector.submissions_file, 'w') as f:
            f.write("not a zip file")
        
        # Should raise exception
        with self.assertRaises(zipfile.BadZipFile):
            self.collector.extract_submissions()
    
    def test_get_company_list(self):
        """Test get_company_list."""
        # Create test companies.json
        companies_data = {
            "0001234567": {
                "name": "Test Company 1",
                "tickers": ["TEST1"],
                "exchanges": ["NYSE"],
                "sic": "1234",
                "category": "Technology",
                "marketCap": 10000000000
            },
            "0001234568": {
                "name": "Test Company 2",
                "tickers": ["TEST2", "TEST2A"],
                "exchanges": ["NASDAQ"],
                "sic": "5678",
                "category": "Healthcare",
                "marketCap": 5000000000
            },
            "0001234569": {
                "name": "Test Company No Ticker",
                "tickers": [],
                "marketCap": 1000000000
            }
        }
        
        companies_file = os.path.join(self.collector.extracted_dir, "companies.json")
        with open(companies_file, 'w') as f:
            json.dump(companies_data, f)
        
        # Get company list
        companies = self.collector.get_company_list()
        
        # Should have 2 companies (third has no ticker)
        self.assertEqual(len(companies), 2)
        
        # Check first company data
        self.assertEqual(companies[0]['cik'], "1234567")
        self.assertEqual(companies[0]['name'], "Test Company 1")
        self.assertEqual(companies[0]['ticker'], "TEST1")
        self.assertEqual(companies[0]['exchange'], "NYSE")
        
        # Test with market cap filter
        companies = self.collector.get_company_list(min_market_cap=6000000000)
        self.assertEqual(len(companies), 1)  # Only the first company should remain

    @patch('src.collectors.submissions_collector.TickerMapper')
    def test_get_company_list_remaps_cached_companies_before_filtering(self, mock_mapper_cls):
        """Cached companies.json should receive fresh ticker mappings before ticker filtering."""
        companies_data = {
            "0002023554": {
                "name": "Sandisk Corporation",
                "tickers": [],
                "exchanges": [],
                "marketCap": 0,
            }
        }

        companies_file = os.path.join(self.collector.extracted_dir, "companies.json")
        with open(companies_file, 'w') as f:
            json.dump(companies_data, f)

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.download_mapping.return_value = True

        def add_sndk(companies):
            companies["0002023554"]["tickers"] = ["SNDK"]
            companies["0002023554"]["exchanges"] = ["Nasdaq"]
            return companies

        mock_mapper.enrich_companies_with_tickers.side_effect = add_sndk

        companies = self.collector.get_company_list()

        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["ticker"], "SNDK")
        self.assertEqual(companies[0]["exchange"], "Nasdaq")
        mock_mapper.download_mapping.assert_called_once()
        mock_mapper.enrich_companies_with_tickers.assert_called_once()
        with open(companies_file, 'r') as f:
            saved = json.load(f)
        self.assertEqual(saved["0002023554"]["tickers"], ["SNDK"])

    def test_get_company_list_keeps_unknown_market_cap_for_later_enrichment(self):
        """Unknown market caps should not be filtered before market-data enrichment."""
        companies_data = {
            "0001234567": {
                "name": "Known Large Cap",
                "tickers": ["BIG"],
                "exchanges": ["NYSE"],
                "marketCap": 10000000000,
            },
            "0001234568": {
                "name": "Known Small Cap",
                "tickers": ["SMALL"],
                "exchanges": ["NASDAQ"],
                "marketCap": 100000000,
            },
            "0001234569": {
                "name": "Unknown Market Cap",
                "tickers": ["UNK"],
                "exchanges": ["NASDAQ"],
                "marketCap": 0,
            },
        }

        companies_file = os.path.join(self.collector.extracted_dir, "companies.json")
        with open(companies_file, 'w') as f:
            json.dump(companies_data, f)

        companies = self.collector.get_company_list(min_market_cap=6000000000)
        tickers = {company["ticker"] for company in companies}

        self.assertEqual(tickers, {"BIG", "UNK"})

if __name__ == '__main__':
    unittest.main()

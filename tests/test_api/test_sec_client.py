"""
Unit tests for SEC API client.
"""

import unittest
import os
import sys
from unittest.mock import patch, Mock

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.sec_client import SECClient

class TestSECClient(unittest.TestCase):
    """Test cases for the SECClient class."""
    
    def setUp(self):
        """Set up test environment."""
        self.user_agent = "Test User (test@example.com)"
        self.sec_client = SECClient(user_agent=self.user_agent, rate_limit_delay=0.01)
    
    def test_initialization(self):
        """Test that client initializes with correct parameters."""
        print("Running test_initialization")  # Debug print
        self.assertEqual(self.sec_client.user_agent, self.user_agent)
        self.assertEqual(self.sec_client.rate_limit_delay, 0.01)
        self.assertEqual(self.sec_client.headers["User-Agent"], self.user_agent)
    
    def test_initialization_fails_without_user_agent(self):
        """Test that initialization fails if user agent not provided."""
        print("Running test_initialization_fails_without_user_agent")  # Debug print
        with self.assertRaises(ValueError):
            SECClient(user_agent="")

if __name__ == '__main__':
    unittest.main()

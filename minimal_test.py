#!/usr/bin/env python3
"""
Minimal test script to debug test discovery issues.
"""

import unittest
import os
import sys
import importlib

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
print(f"Added {project_root} to Python path")

# Check if the API module can be imported
try:
    print("Trying to import SECClient...")
    from src.api.sec_client import SECClient
    print("SECClient imported successfully!")
    
    # Create a simple instance
    client = SECClient("Test User (test@example.com)")
    print("SECClient instance created successfully!")
except Exception as e:
    print(f"Error importing SECClient: {e}")
    sys.exit(1)

# Define a simple test case
class SimpleTest(unittest.TestCase):
    def test_sec_client_import(self):
        from src.api.sec_client import SECClient
        client = SECClient("Test User (test@example.com)")
        self.assertEqual(client.user_agent, "Test User (test@example.com)")
    
    def test_simple(self):
        self.assertTrue(True)

if __name__ == "__main__":
    print("Running minimal tests...")
    unittest.main()

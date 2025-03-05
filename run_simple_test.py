#!/usr/bin/env python3
"""
Simple standalone test for SEC client to verify functionality.
"""

import os
import sys
import unittest

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
print(f"Added {project_root} to Python path")

# Show python path
print("Python path:")
for p in sys.path:
    print(f"  - {p}")

# Check file structure
print("\nFile structure:")
print(f"Project root exists: {os.path.exists(project_root)}")
print(f"src directory exists: {os.path.exists(os.path.join(project_root, 'src'))}")
print(f"src/api directory exists: {os.path.exists(os.path.join(project_root, 'src', 'api'))}")
print(f"src/api/sec_client.py exists: {os.path.exists(os.path.join(project_root, 'src', 'api', 'sec_client.py'))}")

# Define a simple test case for SEC client
class TestSECClient(unittest.TestCase):
    def test_sec_client_import(self):
        try:
            from src.api.sec_client import SECClient
            print("Successfully imported SECClient")
            
            # Create instance
            client = SECClient(user_agent="Test User (test@example.com)")
            print("Successfully created SECClient instance")
            
            # Basic assertions
            self.assertEqual(client.user_agent, "Test User (test@example.com)")
            self.assertEqual(client.headers["User-Agent"], "Test User (test@example.com)")
            
        except ImportError as e:
            print(f"Import error: {e}")
            self.fail(f"Failed to import SECClient: {e}")
    
    def test_initialization_fails_without_user_agent(self):
        try:
            from src.api.sec_client import SECClient
            with self.assertRaises(ValueError):
                SECClient(user_agent="")
            print("Successfully tested initialization failure")
        except ImportError as e:
            self.fail(f"Failed to import SECClient: {e}")

if __name__ == "__main__":
    unittest.main()

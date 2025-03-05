#!/usr/bin/env python3
"""
Simple script to run the unit tests directly without discovery issues.
"""

import os
import sys
import unittest

# Set the working directory to project root
project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(project_root)
sys.path.insert(0, project_root)

print(f"Working directory: {os.getcwd()}")
print(f"Python path: {sys.path[0]}")

# Import test classes directly
try:
    from tests.test_minimal import MinimalTest
    print("Successfully imported MinimalTest")
except ImportError as e:
    print(f"Error importing MinimalTest: {e}")

try:
    from tests.test_api.test_sec_client import TestSECClient
    print("Successfully imported TestSECClient")
except ImportError as e:
    print(f"Error importing TestSECClient: {e}")

# Create test suite manually
suite = unittest.TestSuite()

# Add test cases
suite.addTest(unittest.makeSuite(MinimalTest))

try:
    suite.addTest(unittest.makeSuite(TestSECClient))
except Exception as e:
    print(f"Error adding TestSECClient to suite: {e}")

# Run tests
if __name__ == '__main__':
    print("\nRunning tests...")
    unittest.TextTestRunner(verbosity=2).run(suite)
    print("\nTests completed.")

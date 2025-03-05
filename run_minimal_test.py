#!/usr/bin/env python3
"""
Run a minimal test using unittest directly.
"""

import unittest
import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import the minimal test case
from tests.test_minimal import MinimalTest

if __name__ == '__main__':
    print("Running MinimalTest...")
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
    print("MinimalTest complete")

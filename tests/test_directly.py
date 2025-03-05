#!/usr/bin/env python3
"""
Script to run a specific test directly for debugging.
"""

import os
import sys
import unittest

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
print(f"Added {project_root} to Python path")

# No longer trying to import TestSECClient, just define our own test case

# Define a simple test case
class SimpleDirectTestCase(unittest.TestCase):
    """A simple test case."""
    
    def test_simple(self):
        """Simple test."""
        print("Running simple test directly")
        self.assertTrue(True)

# Run the tests
if __name__ == '__main__':
    # Run specific test
    suite = unittest.TestLoader().loadTestsFromTestCase(SimpleDirectTestCase)
    unittest.TextTestRunner(verbosity=2).run(suite)

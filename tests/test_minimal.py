"""
Minimal test file for debugging.
"""

import unittest
import os
import sys

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class MinimalTest(unittest.TestCase):
    """A minimal test case."""
    
    def test_true(self):
        """Test that True is True."""
        print("Running test_true")
        self.assertTrue(True)
        
    def test_equal(self):
        """Test that 1 equals 1."""
        print("Running test_equal")
        self.assertEqual(1, 1)

if __name__ == '__main__':
    print("Running MinimalTest directly")
    unittest.main()

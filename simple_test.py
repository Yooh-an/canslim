#!/usr/bin/env python3
"""
Simple test to verify unittest is working correctly.
"""

import unittest

class SimpleTest(unittest.TestCase):
    """A very simple test case."""
    
    def test_true(self):
        """Test that True is True."""
        self.assertTrue(True)
    
    def test_equal(self):
        """Test that 1 equals 1."""
        self.assertEqual(1, 1)

if __name__ == '__main__':
    unittest.main()

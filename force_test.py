#!/usr/bin/env python3
"""
Directly run a test by forcing it to execute, bypassing normal test discovery.
"""

import unittest
import os
import sys
import time

print("=" * 60)
print("FORCED TEST EXECUTION")
print("=" * 60)

# Add the project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
print(f"Added {project_root} to sys.path")

# Debug output
print(f"Current working directory: {os.getcwd()}")
print(f"Python path:")
for p in sys.path:
    print(f"  - {p}")

# Define the test directly in this file
class ForceTest(unittest.TestCase):
    def test_forced(self):
        print("RUNNING FORCED TEST")
        self.assertTrue(True, "This test should always pass")

# Run the test directly without discovery
if __name__ == "__main__":
    print("\nRunning test without discovery...")
    test = ForceTest("test_forced")
    result = test.run()
    print(f"Test result: {result.wasSuccessful()}")

    # Also try with manually created test suite
    print("\nRunning test with suite...")
    suite = unittest.TestSuite()
    suite.addTest(ForceTest("test_forced"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print(f"Suite result: {result.wasSuccessful()}")

    print("\nExecution complete")

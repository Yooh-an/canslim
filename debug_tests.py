#!/usr/bin/env python3
"""
Detailed test debugging script.
"""

import os
import sys
import unittest
import inspect
import glob
import importlib.util
from pathlib import Path

def print_separator(title):
    """Print a separator with title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

def check_environment():
    """Check the Python environment and paths."""
    print_separator("ENVIRONMENT CHECK")
    
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Check if we're in the project root
    expected_dirs = ['src', 'tests', 'config']
    existing_dirs = [d for d in expected_dirs if os.path.isdir(d)]
    print(f"Project directories found: {existing_dirs}")
    
    if set(existing_dirs) != set(expected_dirs):
        print(f"WARNING: Not all expected directories found. Missing: {set(expected_dirs) - set(existing_dirs)}")
    
    # Add project root to path if needed
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"Added {project_root} to sys.path")

def find_test_files():
    """Find all test files in the project."""
    print_separator("TEST FILES")
    
    # Look for test files
    test_files = []
    
    # Check if tests directory exists
    if not os.path.exists('tests'):
        print("ERROR: 'tests' directory not found!")
        return []
    
    # Walk through tests directory
    for root, dirs, files in os.walk('tests'):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                test_files.append(os.path.join(root, file))
    
    if test_files:
        print(f"Found {len(test_files)} test files:")
        for file in test_files:
            print(f"  - {file}")
    else:
        print("No test files found matching the pattern 'test_*.py'")
        
    return test_files

def check_test_file(file_path):
    """Check an individual test file for valid test cases."""
    print(f"\nChecking test file: {file_path}")
    
    try:
        # Load the module
        module_name = file_path.replace('/', '.').replace('\\', '.').replace('.py', '')
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find test cases
        test_cases = []
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                test_cases.append(obj)
        
        if test_cases:
            print(f"  Found {len(test_cases)} test case classes:")
            for test_case in test_cases:
                print(f"  - {test_case.__name__}")
                
                # Find test methods
                test_methods = []
                for name, method in inspect.getmembers(test_case):
                    if name.startswith('test_') and callable(method):
                        test_methods.append(name)
                
                if test_methods:
                    print(f"    with {len(test_methods)} test methods: {', '.join(test_methods)}")
                else:
                    print(f"    WARNING: No test methods found in this class!")
        else:
            print("  WARNING: No test case classes found in this file!")
            
    except Exception as e:
        print(f"  ERROR loading test file: {e}")
        import traceback
        traceback.print_exc()

def run_test_file_directly(file_path):
    """Try to run a test file directly."""
    print(f"\nTrying to run test file directly: {file_path}")
    
    original_argv = sys.argv.copy()
    try:
        sys.argv = [file_path]
        
        # Execute the file
        with open(file_path, 'r') as f:
            exec(f.read(), {'__name__': '__main__'})
            
    except Exception as e:
        print(f"  ERROR running test file: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.argv = original_argv

def create_test_file_if_missing():
    """Create a minimal test file if none exist."""
    test_files = glob.glob('tests/**/test_*.py', recursive=True)
    
    if not test_files:
        print("\nNo test files found. Creating a minimal test file...")
        
        # Ensure tests directory exists
        os.makedirs('tests', exist_ok=True)
        
        # Create a minimal test file
        test_file_path = 'tests/test_minimal.py'
        with open(test_file_path, 'w') as f:
            f.write('''"""
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
    unittest.main()
''')
        print(f"Created test file: {test_file_path}")
        return test_file_path
    
    return None

def try_run_unittest_discover():
    """Try to run unittest discover directly."""
    print_separator("RUNNING UNITTEST DISCOVER")
    
    try:
        # Create a test suite
        test_suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
        
        # Count test cases
        test_count = test_suite.countTestCases()
        print(f"Discovered {test_count} test cases")
        
        if test_count == 0:
            print("WARNING: No tests discovered!")
        else:
            # Run the test suite
            runner = unittest.TextTestRunner(verbosity=2)
            runner.run(test_suite)
            
    except Exception as e:
        print(f"ERROR running unittest.discover: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    print("DETAILED TEST DEBUGGING")
    print(f"Current time: {import_time.ctime()}")
    
    # Check environment
    check_environment()
    
    # Find test files
    test_files = find_test_files()
    
    if not test_files:
        created_file = create_test_file_if_missing()
        if created_file:
            test_files = [created_file]
    
    # Check each test file
    print_separator("CHECKING TEST FILES")
    for file_path in test_files:
        check_test_file(file_path)
    
    # Try to run a test file directly (the first one)
    if test_files:
        print_separator("RUNNING TEST FILE DIRECTLY")
        run_test_file_directly(test_files[0])
    
    # Try to run unittest discover directly
    try_run_unittest_discover()
    
    print_separator("DEBUG COMPLETE")

if __name__ == '__main__':
    import time as import_time
    main()

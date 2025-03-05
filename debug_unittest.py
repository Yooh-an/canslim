#!/usr/bin/env python3
"""
Debug unittest module itself.
"""

import unittest
import sys
import os
import importlib

print("=" * 60)
print("UNITTEST MODULE DEBUGGING")
print("=" * 60)

# Basic information
print(f"unittest module location: {unittest.__file__}")
print(f"unittest version: {unittest.__version__ if hasattr(unittest, '__version__') else 'unknown'}")

# Test basic unittest functionality
class BasicTest(unittest.TestCase):
    def test_basic(self):
        print("Running basic test")
        self.assertTrue(True)

def run_basic_test():
    print("\nRunning basic unittest test...")
    
    # Create and run a simple test case
    test = BasicTest("test_basic")
    result = unittest.TestResult()
    test.run(result)
    
    print(f"Test run count: {result.testsRun}")
    print(f"Test errors: {len(result.errors)}")
    print(f"Test failures: {len(result.failures)}")
    
    if result.errors:
        print("Errors:")
        for test, error in result.errors:
            print(f"  {test}: {error}")
    
    if result.failures:
        print("Failures:")
        for test, failure in result.failures:
            print(f"  {test}: {failure}")
    
    return result.wasSuccessful()

def check_python_env():
    """Check Python environment."""
    print("\nPython Environment:")
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Platform: {sys.platform}")
    
    # Check for any potential conflicts or issues
    if sys.platform == 'darwin':  # macOS
        print("Running on macOS, checking for system quirks...")
        # Check if SIP might be interfering with Python
        try:
            sip_result = os.popen('/usr/bin/csrutil status').read()
            print(f"System Integrity Protection status: {sip_result.strip()}")
        except:
            print("Could not check SIP status")

def test_module_loading():
    """Test loading modules directly."""
    print("\nTesting module loading:")
    
    modules_to_test = [
        'unittest',
        'unittest.loader',
        'unittest.suite',
        'unittest.case',
        'unittest.runner'
    ]
    
    for module_name in modules_to_test:
        try:
            module = importlib.import_module(module_name)
            print(f"  ✓ Successfully loaded {module_name}")
        except Exception as e:
            print(f"  ✗ Failed to load {module_name}: {e}")

def manually_discover_tests():
    """Try to manually discover tests."""
    print("\nManually discovering tests:")
    
    # Check if tests directory exists
    if not os.path.exists('tests'):
        print("  ✗ 'tests' directory not found!")
        return
    
    # Find test files
    test_files = []
    for root, _, files in os.walk('tests'):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                test_files.append(os.path.join(root, file))
    
    print(f"Found {len(test_files)} test files:")
    for file in test_files:
        print(f"  - {file}")

    # Try to load each file as a module
    print("\nTrying to load test files as modules:")
    for file_path in test_files:
        try:
            module_name = file_path.replace('/', '.').replace('\\', '.').replace('.py', '')
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None:
                print(f"  ✗ Could not create spec for {file_path}")
                continue
                
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                print(f"  ✓ Successfully loaded {file_path}")
                
                # Find test classes
                test_classes = []
                for name, obj in vars(module).items():
                    if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
                        test_classes.append(obj)
                
                if test_classes:
                    print(f"    Found {len(test_classes)} test classes:")
                    for test_class in test_classes:
                        print(f"      - {test_class.__name__}")
                else:
                    print("    No test classes found")
            except Exception as e:
                print(f"  ✗ Error executing module {file_path}: {e}")
        except Exception as e:
            print(f"  ✗ Error loading {file_path}: {e}")

if __name__ == "__main__":
    # Check basic environment
    check_python_env()
    
    # Test module loading
    test_module_loading()
    
    # Run the basic test
    success = run_basic_test()
    print(f"\nBasic test {'passed' if success else 'failed'}")
    
    # Try manual test discovery
    manually_discover_tests()
    
    print("\nDebugging complete")

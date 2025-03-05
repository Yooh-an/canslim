#!/usr/bin/env python3
"""
Test runner script for Growth Stock Screener.

This script provides an easy way to run different types of tests.
"""

import unittest
import argparse
import sys
import os
import logging

def run_tests(test_type='all', verbosity=2):
    """
    Run the specified tests.
    
    Args:
        test_type: Type of tests to run ('unit', 'integration', 'all')
        verbosity: Verbosity level for test output
    
    Returns:
        True if all tests pass, False otherwise
    """
    # 현재 작업 디렉토리 출력
    print(f"Current working directory: {os.getcwd()}")
    print(f"Looking for tests in: {os.path.join(os.getcwd(), 'tests')}")
    
    # Add project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)
    print(f"Added {project_root} to Python path")
    
    # tests 디렉토리가 존재하는지 확인
    if not os.path.exists('tests'):
        print("Error: 'tests' directory not found!")
        print("Available directories:", [d for d in os.listdir('.') if os.path.isdir(d)])
        return False

    # 디버깅: tests 디렉토리의 내용 출력
    print("Contents of tests directory:", os.listdir('tests'))
    
    loader = unittest.TestLoader()
    runner = unittest.TextTestRunner(verbosity=verbosity)
    
    if test_type == 'unit':
        print("Running unit tests...")
        try:
            # 단위 테스트 실행
            suite = loader.discover('tests', pattern='test_*.py')
            print(f"Discovered {suite.countTestCases()} test cases")
            result = runner.run(suite)
            return result.wasSuccessful()
        except Exception as e:
            print(f"Error discovering unit tests: {e}")
            print(f"Exception type: {type(e)}")
            import traceback
            traceback.print_exc()
            return False
    elif test_type == 'integration':
        print("Running integration tests...")
        try:
            if not os.path.exists('tests/integration'):
                print("Error: 'tests/integration' directory not found!")
                return False
            suite = loader.discover('tests/integration', pattern='test_*.py')
            print(f"Discovered {suite.countTestCases()} integration test cases")
            result = runner.run(suite)
            return result.wasSuccessful()
        except Exception as e:
            print(f"Error discovering integration tests: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:  # 'all'
        print("Running all tests...")
        try:
            suite = loader.discover('tests', pattern='test_*.py')
            print(f"Discovered {suite.countTestCases()} total test cases")
            result = runner.run(suite)
            return result.wasSuccessful()
        except Exception as e:
            print(f"Error discovering tests: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Parse arguments and run tests."""
    parser = argparse.ArgumentParser(description='Run tests for Growth Stock Screener')
    parser.add_argument(
        '--type',
        choices=['unit', 'integration', 'all'],
        default='all',
        help='Type of tests to run (default: all)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Increase output verbosity'
    )
    
    args = parser.parse_args()
    verbosity = 2 if args.verbose else 1
    
    # Set working directory to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"Changed working directory to: {script_dir}")
    
    success = run_tests(args.type, verbosity)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

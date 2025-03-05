#!/usr/bin/env python3
"""
Test if modules can be imported correctly.
"""

import os
import sys
import traceback

# Add the project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

print("=" * 60)
print("IMPORT TEST")
print("=" * 60)

print(f"Current directory: {os.getcwd()}")
print(f"Project root added to path: {project_root}")

# List of modules to test importing
modules_to_test = [
    'src',
    'src.api',
    'src.api.sec_client',
    'src.utils',
    'src.utils.logger',
    'tests',
    'tests.test_minimal'
]

# Try to import each module
for module_name in modules_to_test:
    print(f"\nTrying to import {module_name}...")
    try:
        module = __import__(module_name, fromlist=['*'])
        print(f"✓ Successfully imported {module_name}")
        print(f"  Module location: {getattr(module, '__file__', 'unknown')}")
    except ImportError as e:
        print(f"✗ Failed to import {module_name}: {e}")
        print("  Traceback:")
        traceback.print_exc()
    except Exception as e:
        print(f"✗ Error when importing {module_name}: {e}")
        print("  Traceback:")
        traceback.print_exc()

# Try to specifically load the SEC client class
print("\n" + "=" * 60)
print("TRYING TO LOAD SEC CLIENT CLASS")
print("=" * 60)

try:
    from src.api.sec_client import SECClient
    print("✓ Successfully imported SECClient class")
    
    # Try to create an instance
    client = SECClient("Test User (test@example.com)")
    print("✓ Successfully created SECClient instance")
    print(f"  User agent: {client.user_agent}")
except Exception as e:
    print(f"✗ Error with SECClient: {e}")
    traceback.print_exc()

# Check file existence directly
print("\n" + "=" * 60)
print("CHECKING FILES DIRECTLY")
print("=" * 60)

files_to_check = [
    'src/__init__.py', 
    'src/api/__init__.py', 
    'src/api/sec_client.py',
    'tests/__init__.py',
    'tests/test_api/__init__.py',
    'tests/test_minimal.py'
]

for file_path in files_to_check:
    if os.path.isfile(file_path):
        print(f"✓ File exists: {file_path}")
    else:
        print(f"✗ File missing: {file_path}")

print("\nImport test complete")

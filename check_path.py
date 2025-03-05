#!/usr/bin/env python3
"""
Check Python module import paths.
"""

import sys

print("Python version:", sys.version)
print("Python path:")
for p in sys.path:
    print(f"  - {p}")

import os
print("\nCurrent directory:", os.getcwd())
print("Directory contents:", os.listdir("."))

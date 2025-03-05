#!/usr/bin/env python3
"""
Inspect a file to check its contents.
"""

import os
import sys
import importlib.util
import ast

def print_separator(title):
    """Print a separator with title."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

def inspect_file(file_path):
    """Inspect a Python file for classes, functions, etc."""
    print_separator(f"INSPECTING {file_path}")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    print(f"File exists: {file_path}")
    print(f"File size: {os.path.getsize(file_path)} bytes")
    
    # Print file content (first 50 lines or so)
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            print(f"\nFile content (first 50 lines):")
            print("-----------------------------------")
            for i, line in enumerate(lines[:50]):
                print(f"{i+1:3d}: {line}", end="")
            if len(lines) > 50:
                print("... (truncated)")
    except Exception as e:
        print(f"Error reading file: {e}")
    
    # Parse the Python file using AST
    try:
        with open(file_path, 'r') as f:
            file_content = f.read()
            parsed = ast.parse(file_content)
            
        classes = [node for node in ast.walk(parsed) if isinstance(node, ast.ClassDef)]
        functions = [node for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef)]
        
        print(f"\nClasses defined in the file ({len(classes)}):")
        for cls in classes:
            print(f"  - {cls.name}")
            methods = [node.name for node in ast.walk(cls) if isinstance(node, ast.FunctionDef)]
            if methods:
                print(f"    Methods: {', '.join(methods)}")
        
        print(f"\nFunctions defined at module level ({len(functions) - sum(1 for c in classes for _ in ast.walk(c) if isinstance(_, ast.FunctionDef))}):")
        for func in functions:
            if func.name not in [m for c in classes for m in [node.name for node in ast.walk(c) if isinstance(node, ast.FunctionDef)]]:
                print(f"  - {func.name}")
        
        return True
    except SyntaxError as e:
        print(f"Syntax error in file: {e}")
        return False
    except Exception as e:
        print(f"Error analyzing file: {e}")
        return False

def try_import_module(module_path):
    """Try to import a module and inspect it."""
    print_separator(f"TRYING TO IMPORT {module_path}")
    
    try:
        # Convert path to module name
        module_name = module_path.replace('/', '.').replace('\\', '.').replace('.py', '')
        
        # Try importing
        print(f"Importing module {module_name}...")
        module = importlib.__import__(module_name, fromlist=['*'])
        
        print(f"Successfully imported {module_name}")
        print(f"Module file: {module.__file__}")
        
        # List module contents
        print("\nModule contents:")
        for name in dir(module):
            if not name.startswith('__'):
                try:
                    obj = getattr(module, name)
                    if isinstance(obj, type):
                        print(f"  - Class: {name}")
                    elif callable(obj):
                        print(f"  - Function/Method: {name}")
                    else:
                        print(f"  - Other: {name}")
                except Exception as e:
                    print(f"  - Error getting {name}: {e}")
        
        return True
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python inspect_file.py <file_path> [try_import]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    success = inspect_file(file_path)
    
    # Optionally try to import
    if len(sys.argv) > 2 and sys.argv[2] == 'try_import':
        # Add project root to sys.path
        project_root = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, project_root)
        try_import_module(file_path)

"""
Performance utilities for the Growth Stock Screener.

This module provides utilities for measuring and improving performance.
"""

import time
import functools
from typing import Dict, Any, Callable, Optional
import logging
from functools import lru_cache

# Dictionary to store execution times for profiling
execution_times: Dict[str, float] = {}

def timed(func: Callable) -> Callable:
    """
    Decorator to measure the execution time of a function.
    
    Args:
        func: Function to be measured
        
    Returns:
        Wrapped function that measures execution time
    """
    @functools.wraps(func)
    def wrapper_timed(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Store execution time
        func_name = func.__qualname__
        if func_name not in execution_times:
            execution_times[func_name] = 0
        execution_times[func_name] += execution_time
        
        # Log execution time
        logger = logging.getLogger("performance")
        logger.debug(f"{func_name} took {execution_time:.4f} seconds to execute.")
        
        return result
    return wrapper_timed

def get_execution_times() -> Dict[str, float]:
    """
    Get the recorded execution times.
    
    Returns:
        Dictionary mapping function names to total execution time
    """
    return execution_times

def reset_execution_times() -> None:
    """Reset the recorded execution times."""
    execution_times.clear()

def get_slowest_functions(n: int = 10) -> Dict[str, float]:
    """
    Get the slowest functions.
    
    Args:
        n: Number of functions to return
        
    Returns:
        Dictionary of the n slowest functions with their execution times
    """
    sorted_items = sorted(execution_times.items(), key=lambda x: x[1], reverse=True)
    return dict(sorted_items[:n])

def profile(func: Optional[Callable] = None, *, record: bool = True) -> Callable:
    """
    Profile a function to measure its execution time.
    
    Args:
        func: Function to profile
        record: Whether to record the execution time in the global dictionary
        
    Returns:
        Profiled function
    """
    if func is None:
        return lambda f: profile(f, record=record)
    
    @functools.wraps(func)
    def wrapper_profile(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        
        func_name = func.__qualname__
        logger = logging.getLogger("performance")
        logger.info(f"{func_name} took {execution_time:.4f} seconds to execute.")
        
        if record:
            if func_name not in execution_times:
                execution_times[func_name] = 0
            execution_times[func_name] += execution_time
        
        return result
    
    return wrapper_profile

# Add a memory-based cache decorator for performance optimization
def memoize(func: Callable) -> Callable:
    """
    Decorator to cache the results of a function in memory.
    
    Args:
        func: Function to cache
        
    Returns:
        Cached function
    """
    return lru_cache(maxsize=128)(func)

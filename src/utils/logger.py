"""
Logging utilities for the Growth Stock Screener application.
"""

import logging
import os
from pathlib import Path

# Try to import colorlog, but handle case where it's not installed
try:
    import colorlog
    has_colorlog = True
except ImportError:
    has_colorlog = False

def setup_logger(name, log_file=None, level=logging.INFO):
    """
    Set up a logger with specified name, file, and level.
    
    Args:
        name: Logger name
        log_file: Optional log file path
        level: Logging level
        
    Returns:
        Configured logger
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicate logging
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatters
    if has_colorlog:
        # Use ColoredFormatter instead of ColorFormatter
        color_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        formatter = color_formatter
    else:
        # Standard formatter if colorlog is not available
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # Optionally add file handler
    if log_file:
        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            
        # Add file handler (without colors for log file)
        plain_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(log_file)
        fh.setLevel(level)
        fh.setFormatter(plain_formatter)
        logger.addHandler(fh)
    
    return logger

"""
Logger module for the Growth Stock Screener application.
Provides consistent logging across the application.
"""

import logging
import os
from pathlib import Path
import colorlog

# Set up color formatter
color_formatter = colorlog.ColorFormatter(
    "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    },
)

# Standard formatter (for file output without colors)
standard_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name, log_file=None, level=logging.INFO):
    """
    Setup logger with colored console output and optional file output.
    
    Args:
        name: Name of the logger
        log_file: Optional log file path
        level: Logging level (default: INFO)
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding handlers multiple times if called more than once
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(color_formatter)
    logger.addHandler(console_handler)
    
    # File handler if log_file is provided
    if log_file:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(standard_formatter)
        logger.addHandler(file_handler)
    
    return logger

# Create utils/__init__.py to make it a package

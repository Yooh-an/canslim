"""
Logging utility module for the application.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

def setup_logger(name: str, log_file: Optional[str] = None, level: Optional[int] = None, log_level: Optional[str] = None) -> logging.Logger:
    """
    Set up a logger with specified name, file, and level.
    
    Args:
        name: Logger name
        log_file: Optional file path to write logs to
        level: Optional logging level as an int
        log_level: Optional logging level as a string (e.g., "DEBUG", "INFO")
        
    Returns:
        Configured logger
    """
    # Convert string log level to int if provided
    if log_level and not level:
        level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Default to INFO if no level specified
    if level is None:
        level = logging.INFO
        
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Add file handler if log file specified
    if log_file:
        # Create directory for log file if it doesn't exist
        log_dir = os.path.dirname(log_file)
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        
        # Use a rotating file handler (max 5MB, keep 3 backups)
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

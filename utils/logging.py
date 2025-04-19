"""Logging configuration."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

def setup_logging(log_level: Optional[str] = None, log_file: Optional[str] = None,
               max_bytes: int = 2 * 1024 * 1024, backup_count: int = 5):
    """Configure logging for the application.
    
    Args:
        log_level: Log level to use (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file
        max_bytes: Maximum size of each log file in bytes (default: 2 MB)
        backup_count: Number of backup files to keep (default: 5)
    """
    # Set defaults
    log_level = log_level or "INFO"
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if log file is specified)
    if log_file:
        # Create directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set levels for specific modules
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    
    return root_logger
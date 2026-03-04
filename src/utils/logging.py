from __future__ import annotations

from typing import Optional
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(
    level: str, 
    log_format: str,
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    ) -> None:
    """Set up logging configuration for the crawler.
    
    Args:
        level (str): The logging level (e.g., "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL").
        log_format (str): The format for log messages.
        log_file (Optional[str]): The file path to save logs. If None, logs will only be printed to console.
        max_bytes (int): The maximum size of the log file before it gets rotated.
        backup_count (int): The number of backup log files to keep.
    """
    
    
    if log_format is None:
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        
    main_logger = logging.getLogger()
    main_logger.setLevel(getattr(logging, level.upper()))
    
    main_logger.handlers.clear()
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(logging.Formatter(log_format))
    main_logger.addHandler(console_handler)
    
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_bytes, 
            backupCount=backup_count, 
            encoding='utf-8', 
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(logging.Formatter(log_format))
        main_logger.addHandler(file_handler)
        
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

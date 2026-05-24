"""
Logging configuration.
"""
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: Path, level: str = "INFO") -> None:
    """Setup logging with both file and console handlers."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Root logger
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))
    
    # File handler (rotating)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setFormatter(
        logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    )
    root.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(levelname)s: %(message)s')
    )
    root.addHandler(console_handler)

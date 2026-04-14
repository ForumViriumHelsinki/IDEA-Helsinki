# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
import logging
import sys
from logging.handlers import RotatingFileHandler


class Logger:
    """A simple, configurable class for performing logging to the console and/or a file."""

    def __init__(self, name: str, level=logging.INFO, log_file: str | None = None):
        """Initializes the logger.

        Args:
            name (str): The name for the logger, typically __name__.
            level: The logging level (e.g., logging.DEBUG, logging.INFO).
            log_file (str, optional): Path to a log file. If provided, logs
                                      will be written to this file. Defaults to None.

        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = (
            False  # Prevent logs from propagating to the root logger
        )

        # Only add handlers if none exist yet
        if not self.logger.hasHandlers():
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            # Console Handler (always on)
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # File Handler (optional)
            if log_file:
                # Use a rotating file handler for long-running services
                file_handler = RotatingFileHandler(
                    log_file,
                    maxBytes=10 * 1024 * 1024,
                    backupCount=5,  # 10 MB per file, 5 backups
                )
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

    def info(self, message):
        """Log an info-level message."""
        self.logger.info(message)

    def warning(self, message):
        """Log a warning-level message."""
        self.logger.warning(message)

    def error(self, message, exc_info=False):
        """Log an error-level message."""
        self.logger.error(message, exc_info=exc_info)

    def critical(self, message, exc_info=False):
        """Log a critical-level message."""
        self.logger.critical(message, exc_info=exc_info)

    def debug(self, message):
        """Log a debug-level message."""
        self.logger.debug(message)

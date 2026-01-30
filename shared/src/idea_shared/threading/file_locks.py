"""
Thread-safe file locking for segment mapping files.
"""

import errno
import json
import logging
import os
import random
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ESTALE error number (116 on Linux, may differ on other systems)
ESTALE = getattr(errno, "ESTALE", 116)


def atomic_write_json(
    filepath: str | Path,
    data: dict | list,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> bool:
    """
    Write JSON atomically using temp file + rename pattern with ESTALE retry.

    Uses write-to-temp-then-rename strategy to ensure readers always
    get a complete, consistent file. Implements exponential backoff
    retry for ESTALE (errno 116) errors that occur with NFS/hostPath mounts.

    Args:
        filepath: Target file path
        data: Dictionary or list data to write as JSON
        max_retries: Maximum retry attempts for ESTALE errors (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)

    Returns:
        bool: True if successful

    Raises:
        OSError: If write fails after all retries
    """
    filepath = Path(filepath)
    temp_file = filepath.with_suffix(filepath.suffix + ".tmp")

    for attempt in range(max_retries + 1):
        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            # Atomic rename (POSIX systems)
            os.rename(temp_file, filepath)
            return True

        except OSError as e:
            # Check for ESTALE (Stale file handle) error
            if e.errno == ESTALE and attempt < max_retries:
                delay = base_delay * (2**attempt) + random.uniform(0, 0.5)
                logger.warning(
                    f"ESTALE error writing to {filepath}, attempt {attempt + 1}/{max_retries + 1}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            # Clean up temp file if it exists
            _cleanup_temp_file(temp_file)
            raise

        except Exception:
            _cleanup_temp_file(temp_file)
            raise


def _cleanup_temp_file(temp_file: Path) -> None:
    """Clean up temporary file if it exists."""
    try:
        if temp_file.exists():
            os.remove(temp_file)
    except Exception:
        pass


class SegmentMappingFileManager:
    """Thread-safe manager for segment mapping file operations."""

    def __init__(self):
        """Initialize the file manager with a lock."""
        self._lock = threading.Lock()

    def write_mapping_atomic(self, data: dict, file_path: str):
        """
        Write segment mapping data with atomic rename to prevent corruption.

        Uses write-to-temp-then-rename strategy to ensure readers always
        get a complete, consistent file even if write is interrupted.

        Args:
            data: Dictionary data to write as JSON
            file_path: Target file path

        Returns:
            bool: True if successful, False otherwise
        """
        with self._lock:
            try:
                temp_file = f"{file_path}.tmp"

                # Write to temporary file
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)

                # Atomic rename (POSIX systems)
                os.rename(temp_file, file_path)
                return True

            except Exception as e:
                # Clean up temp file if it exists
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                raise e

    def read_mapping_safe(self, file_path: str) -> dict:
        """
        Thread-safe read of segment mapping file.

        Args:
            file_path: File path to read

        Returns:
            dict: Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON
        """
        with self._lock:
            with open(file_path) as f:
                return json.load(f)

    def write_json_safe(self, data: dict | list, file_path: str):
        """
        Thread-safe write of JSON data (non-atomic, for non-critical files).

        Args:
            data: Data to write
            file_path: Target file path

        Returns:
            bool: True if successful
        """
        with self._lock:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
            return True

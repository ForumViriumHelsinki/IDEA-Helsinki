"""
Thread-safe file locking for segment mapping files.
"""

import json
import os
import threading


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

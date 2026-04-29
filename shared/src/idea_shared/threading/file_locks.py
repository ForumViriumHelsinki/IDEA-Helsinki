"""Thread-safe file locking for segment mapping files."""

import errno
import json
import logging
import os
import random
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ESTALE error number (116 on Linux, may differ on other systems)
ESTALE = getattr(errno, "ESTALE", 116)


def read_json_with_retry(
    filepath: str | Path,
    max_retries: int = 3,
    base_delay: float = 0.5,
) -> dict | list | None:
    """Read JSON with ESTALE retry for GCS FUSE mounts.

    Retries on ESTALE (stale file handle) with exponential backoff + jitter.
    On JSONDecodeError, retries once (writer may have been mid-close), then
    returns None with a warning.

    Args:
        filepath: Path to JSON file
        max_retries: Maximum retry attempts for ESTALE errors
        base_delay: Base delay in seconds for exponential backoff

    Returns:
        Parsed JSON data, or None if file is missing, empty, or unreadable

    """
    filepath = Path(filepath)

    for attempt in range(max_retries + 1):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            if attempt < 1:
                delay = base_delay + random.uniform(0, 0.3)
                logger.warning(
                    f"JSONDecodeError reading {filepath}: {e}. "
                    f"Retrying in {delay:.1f}s (writer may be mid-close)..."
                )
                time.sleep(delay)
                continue
            logger.warning(f"JSONDecodeError reading {filepath} after retry: {e}")
            return None
        except OSError as e:
            if e.errno == ESTALE and attempt < max_retries:
                delay = base_delay * (2**attempt) + random.uniform(0, 0.3)
                logger.warning(
                    f"ESTALE error reading {filepath}, attempt {attempt + 1}/{max_retries + 1}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            if e.errno == ESTALE:
                logger.error(
                    f"ESTALE error reading {filepath} after {max_retries + 1} attempts"
                )
                return None
            raise


def atomic_write_json(
    filepath: str | Path,
    data: dict | list,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> bool:
    """Write JSON atomically using secure temp file + rename pattern with ESTALE retry.

    Uses tempfile.NamedTemporaryFile with unpredictable names and O_EXCL flag
    to prevent symlink attacks, then renames to target path atomically.
    Implements exponential backoff retry for ESTALE (errno 116) errors that
    occur with GCS FUSE mounts.

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

    for attempt in range(max_retries + 1):
        temp_fd = None
        temp_path = None
        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Create secure temporary file with unpredictable name
            # delete=False because we need to rename it (rename closes the file)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=filepath.parent,
                prefix=f".{filepath.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                temp_path = Path(f.name)
                temp_fd = f.fileno()
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(temp_fd)  # Force write to disk

            # Atomic rename (POSIX systems)
            os.rename(temp_path, filepath)
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
                # Clean up failed temp file if it exists
                if temp_path:
                    _cleanup_temp_file(temp_path)
                continue
            # Clean up temp file if it exists
            if temp_path:
                _cleanup_temp_file(temp_path)
            raise

        except Exception:
            if temp_path:
                _cleanup_temp_file(temp_path)
            raise

    return False


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
        """Write segment mapping data with atomic rename to prevent corruption.

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
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Atomic rename (POSIX systems)
                os.rename(temp_file, file_path)
                return True

            except Exception:
                # Clean up temp file if it exists
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                raise

    def read_mapping_safe(self, file_path: str) -> dict:
        """Thread-safe read of segment mapping file with ESTALE retry for GCS FUSE mounts.

        Args:
            file_path: File path to read

        Returns:
            dict: Parsed JSON data, or empty dict if unreadable

        Raises:
            FileNotFoundError: If file doesn't exist

        """
        with self._lock:
            data = read_json_with_retry(file_path)
            if data is None:
                if not Path(file_path).exists():
                    raise FileNotFoundError(f"File not found: {file_path}")
                return {}
            if not isinstance(data, dict):
                return {}
            return data

    def write_json_safe(self, data: dict | list, file_path: str):
        """Thread-safe write of JSON data (non-atomic, for non-critical files).

        Args:
            data: Data to write
            file_path: Target file path

        Returns:
            bool: True if successful

        """
        with self._lock:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True

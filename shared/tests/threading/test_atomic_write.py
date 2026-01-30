"""Tests for atomic_write_json utility in file_locks.py."""

import errno
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from idea_shared.threading.file_locks import ESTALE, _cleanup_temp_file, atomic_write_json


class TestAtomicWriteJson:
    """Tests for atomic_write_json function."""

    def test_atomic_write_success(self, tmp_path: Path):
        """Test successful atomic write creates valid JSON file."""
        test_file = tmp_path / "test.json"
        test_data = {"key": "value", "nested": {"a": 1, "b": 2}}

        result = atomic_write_json(test_file, test_data)

        assert result is True
        assert test_file.exists()
        with open(test_file) as f:
            written_data = json.load(f)
        assert written_data == test_data

    def test_atomic_write_creates_parent_directories(self, tmp_path: Path):
        """Test atomic write creates parent directories if they don't exist."""
        test_file = tmp_path / "subdir" / "nested" / "test.json"
        test_data = {"created": True}

        result = atomic_write_json(test_file, test_data)

        assert result is True
        assert test_file.exists()

    def test_atomic_write_overwrites_existing_file(self, tmp_path: Path):
        """Test atomic write correctly overwrites existing file."""
        test_file = tmp_path / "test.json"
        old_data = {"old": "data"}
        new_data = {"new": "data"}

        # Write initial data
        with open(test_file, "w") as f:
            json.dump(old_data, f)

        # Overwrite with atomic write
        result = atomic_write_json(test_file, new_data)

        assert result is True
        with open(test_file) as f:
            written_data = json.load(f)
        assert written_data == new_data

    def test_atomic_write_temp_file_cleaned_on_success(self, tmp_path: Path):
        """Test temporary file is removed after successful write."""
        test_file = tmp_path / "test.json"

        atomic_write_json(test_file, {"data": True})

        # No temp files should remain (with any prefix pattern)
        temp_files = list(tmp_path.glob(".test.json.*.tmp"))
        assert len(temp_files) == 0

    def test_atomic_write_with_list_data(self, tmp_path: Path):
        """Test atomic write handles list data correctly."""
        test_file = tmp_path / "test.json"
        test_data = [1, 2, {"nested": "dict"}]

        result = atomic_write_json(test_file, test_data)

        assert result is True
        with open(test_file) as f:
            written_data = json.load(f)
        assert written_data == test_data

    def test_atomic_write_accepts_path_string(self, tmp_path: Path):
        """Test atomic write accepts string path in addition to Path object."""
        test_file = str(tmp_path / "test.json")
        test_data = {"string_path": True}

        result = atomic_write_json(test_file, test_data)

        assert result is True
        assert Path(test_file).exists()

    def test_atomic_write_uses_unpredictable_temp_names(self, tmp_path: Path):
        """Test that temporary files use unpredictable names (security)."""
        test_file = tmp_path / "test.json"
        temp_names = []

        # Mock NamedTemporaryFile to capture temp file names
        original_named_temp = tempfile.NamedTemporaryFile

        def capture_temp_name(*args, **kwargs):
            temp_file = original_named_temp(*args, **kwargs)
            temp_names.append(Path(temp_file.name).name)
            return temp_file

        with patch("tempfile.NamedTemporaryFile", side_effect=capture_temp_name):
            atomic_write_json(test_file, {"data": True})

        # Verify temp file name is NOT predictable (not just "test.json.tmp")
        assert len(temp_names) == 1
        temp_name = temp_names[0]
        # Should have unpredictable component (random chars from tempfile)
        assert temp_name.startswith(".test.json.")
        assert temp_name.endswith(".tmp")
        # Should have random component between prefix and suffix
        # (tempfile adds random chars, length varies but should be > prefix + suffix)
        assert len(temp_name) > len(".test.json.tmp")


class TestAtomicWriteEstaleRetry:
    """Tests for ESTALE error retry logic."""

    def test_estale_retry_succeeds_after_transient_error(self, tmp_path: Path):
        """Test retry succeeds after transient ESTALE error."""
        test_file = tmp_path / "test.json"
        test_data = {"retry": "test"}

        call_count = 0
        original_rename = os.rename

        def mock_rename_with_estale(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on first attempt, succeed on second
            if call_count == 1:
                error = OSError("Stale file handle")
                error.errno = ESTALE
                raise error
            return original_rename(*args, **kwargs)

        with patch("os.rename", side_effect=mock_rename_with_estale):
            with patch("time.sleep"):  # Skip actual sleep
                result = atomic_write_json(test_file, test_data)

        assert result is True
        assert call_count == 2

    def test_estale_retry_exhausted_raises_error(self, tmp_path: Path):
        """Test raises OSError after max retries exhausted."""
        test_file = tmp_path / "test.json"
        test_data = {"fail": "always"}

        def always_fail(*args, **kwargs):
            error = OSError("Stale file handle")
            error.errno = ESTALE
            raise error

        with patch("os.rename", side_effect=always_fail):
            with patch("time.sleep"):  # Skip actual sleep
                with pytest.raises(OSError) as exc_info:
                    atomic_write_json(test_file, test_data, max_retries=3)

        assert exc_info.value.errno == ESTALE

    def test_estale_retry_uses_exponential_backoff(self, tmp_path: Path):
        """Test exponential backoff timing on ESTALE errors."""
        test_file = tmp_path / "test.json"
        sleep_times = []

        def capture_sleep(seconds):
            sleep_times.append(seconds)

        def always_fail(*args, **kwargs):
            error = OSError("Stale file handle")
            error.errno = ESTALE
            raise error

        with patch("os.rename", side_effect=always_fail):
            with patch("time.sleep", side_effect=capture_sleep):
                with patch("random.uniform", return_value=0.25):  # Fixed jitter
                    with pytest.raises(OSError):
                        atomic_write_json(test_file, {}, max_retries=3, base_delay=1.0)

        # Verify exponential backoff: 1*2^0 + jitter, 1*2^1 + jitter, 1*2^2 + jitter
        assert len(sleep_times) == 3
        assert sleep_times[0] == pytest.approx(1.25, rel=0.01)  # 1.0 + 0.25
        assert sleep_times[1] == pytest.approx(2.25, rel=0.01)  # 2.0 + 0.25
        assert sleep_times[2] == pytest.approx(4.25, rel=0.01)  # 4.0 + 0.25

    def test_non_estale_error_not_retried(self, tmp_path: Path):
        """Test non-ESTALE errors are not retried."""
        test_file = tmp_path / "test.json"
        call_count = 0

        def fail_with_permission_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            error = OSError("Permission denied")
            error.errno = errno.EACCES
            raise error

        with patch("os.rename", side_effect=fail_with_permission_error):
            with pytest.raises(OSError) as exc_info:
                atomic_write_json(test_file, {})

        assert call_count == 1  # No retry for non-ESTALE errors
        assert exc_info.value.errno == errno.EACCES


class TestCleanupTempFile:
    """Tests for _cleanup_temp_file helper function."""

    def test_cleanup_removes_existing_file(self, tmp_path: Path):
        """Test cleanup removes existing temp file."""
        temp_file = tmp_path / "test.tmp"
        temp_file.write_text("temp content")

        _cleanup_temp_file(temp_file)

        assert not temp_file.exists()

    def test_cleanup_handles_nonexistent_file(self, tmp_path: Path):
        """Test cleanup handles nonexistent file gracefully."""
        temp_file = tmp_path / "nonexistent.tmp"

        # Should not raise
        _cleanup_temp_file(temp_file)

    def test_cleanup_handles_removal_error(self, tmp_path: Path):
        """Test cleanup handles errors during removal gracefully."""
        temp_file = tmp_path / "test.tmp"
        temp_file.write_text("temp content")

        with patch("os.remove", side_effect=PermissionError("Cannot remove")):
            # Should not raise
            _cleanup_temp_file(temp_file)

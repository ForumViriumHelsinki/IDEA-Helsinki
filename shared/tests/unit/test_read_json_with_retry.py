"""Tests for read_json_with_retry function."""

import json
from unittest.mock import patch

import pytest

from idea_shared.threading.file_locks import ESTALE, read_json_with_retry


@pytest.mark.unit
class TestReadJsonWithRetry:
    """Tests for read_json_with_retry."""

    def test_reads_valid_json(self, tmp_path):
        """Successfully reads a valid JSON file."""
        filepath = tmp_path / "test.json"
        expected = {"key": "value", "count": 42}
        filepath.write_text(json.dumps(expected))

        result = read_json_with_retry(filepath)

        assert result == expected

    def test_reads_json_list(self, tmp_path):
        """Successfully reads a JSON list."""
        filepath = tmp_path / "test.json"
        expected = [1, 2, 3]
        filepath.write_text(json.dumps(expected))

        result = read_json_with_retry(filepath)

        assert result == expected

    def test_returns_none_for_missing_file(self, tmp_path):
        """Returns None when file doesn't exist."""
        filepath = tmp_path / "nonexistent.json"

        result = read_json_with_retry(filepath)

        assert result is None

    def test_retries_on_estale_then_succeeds(self, tmp_path):
        """Retries on ESTALE error and succeeds on subsequent attempt."""
        filepath = tmp_path / "test.json"
        expected = {"data": "ok"}
        filepath.write_text(json.dumps(expected))

        call_count = 0
        original_open = open

        def mock_open_fn(path, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError(ESTALE, "Stale file handle")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            result = read_json_with_retry(filepath, base_delay=0.01)

        assert result == expected
        assert call_count == 2

    def test_returns_none_after_max_estale_retries(self, tmp_path):
        """Returns None when ESTALE persists beyond max retries."""
        filepath = tmp_path / "test.json"
        filepath.write_text('{"key": "value"}')

        def always_estale(path, *args, **kwargs):
            raise OSError(ESTALE, "Stale file handle")

        with patch("builtins.open", side_effect=always_estale):
            result = read_json_with_retry(filepath, max_retries=2, base_delay=0.01)

        assert result is None

    def test_retries_on_json_decode_error_then_succeeds(self, tmp_path):
        """Retries once on JSONDecodeError (writer mid-close), then succeeds."""
        filepath = tmp_path / "test.json"
        expected = {"data": "ok"}

        call_count = 0
        original_open = open

        def mock_open_fn(path, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulate truncated JSON from mid-write
                from io import StringIO

                return StringIO('{"data": "ok"')  # Missing closing brace
            return original_open(path, *args, **kwargs)

        # Write valid JSON for the retry
        filepath.write_text(json.dumps(expected))

        with patch("builtins.open", side_effect=mock_open_fn):
            result = read_json_with_retry(filepath, base_delay=0.01)

        assert result == expected

    def test_returns_none_on_persistent_json_decode_error(self, tmp_path):
        """Returns None when JSON is persistently invalid."""
        filepath = tmp_path / "test.json"
        filepath.write_text("not json at all {{{")

        result = read_json_with_retry(filepath, base_delay=0.01)

        assert result is None

    def test_raises_non_estale_os_error(self, tmp_path):
        """Raises non-ESTALE OSError immediately (no retry)."""
        filepath = tmp_path / "test.json"
        filepath.write_text('{"key": "value"}')

        import errno

        def permission_denied(path, *args, **kwargs):
            raise OSError(errno.EACCES, "Permission denied")

        with patch("builtins.open", side_effect=permission_denied):
            with pytest.raises(OSError, match="Permission denied"):
                read_json_with_retry(filepath)

    def test_accepts_string_path(self, tmp_path):
        """Accepts string path in addition to Path objects."""
        filepath = tmp_path / "test.json"
        expected = {"key": "value"}
        filepath.write_text(json.dumps(expected))

        result = read_json_with_retry(str(filepath))

        assert result == expected

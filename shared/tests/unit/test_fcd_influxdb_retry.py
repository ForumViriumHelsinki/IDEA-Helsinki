"""Tests for FCDInfluxDBManager operation-level retry logic."""

from http.client import IncompleteRead, RemoteDisconnected
from unittest.mock import MagicMock, patch

import pytest

from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager


@pytest.fixture
def manager():
    """Create a FCDInfluxDBManager with mocked InfluxDB client."""
    with patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mgr = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test",
            org="test-org",
            bucket="test-bucket",
        )
        yield mgr


class TestInfluxDBQueryRetry:
    """Test retry on transient errors for query methods."""

    @pytest.mark.unit
    def test_retries_on_remote_disconnected(self, manager):
        """RemoteDisconnected should trigger retry."""
        manager.query_api.query.side_effect = RemoteDisconnected("peer closed")

        with pytest.raises(RemoteDisconnected):
            manager.get_last_update_timestamp()

        assert manager.query_api.query.call_count == 3

    @pytest.mark.unit
    def test_retries_on_incomplete_read(self, manager):
        """IncompleteRead should trigger retry."""
        manager.query_api.query.side_effect = IncompleteRead(b"", 100)

        with pytest.raises(IncompleteRead):
            manager.get_last_update_timestamp()

        assert manager.query_api.query.call_count == 3

    @pytest.mark.unit
    def test_retries_on_connection_error(self, manager):
        """ConnectionError should trigger retry."""
        manager.query_api.query.side_effect = ConnectionError("refused")

        with pytest.raises(ConnectionError):
            manager.get_last_update_timestamp()

        assert manager.query_api.query.call_count == 3

    @pytest.mark.unit
    def test_succeeds_after_transient_failure(self, manager):
        """Should succeed on second attempt after transient failure."""
        mock_record = MagicMock()
        mock_record.get_time.return_value = "2024-01-01T00:00:00Z"
        mock_table = MagicMock()
        mock_table.records = [mock_record]

        manager.query_api.query.side_effect = [
            RemoteDisconnected("peer closed"),
            [mock_table],
        ]

        result = manager.get_last_update_timestamp()

        assert result == "2024-01-01T00:00:00Z"
        assert manager.query_api.query.call_count == 2


class TestInfluxDBNoRetryOnPermanentErrors:
    """Test that permanent errors are NOT retried."""

    @pytest.mark.unit
    def test_no_retry_on_value_error(self, manager):
        """ValueError should not be retried."""
        manager.query_api.query.side_effect = ValueError("bad query")

        with pytest.raises(ValueError):
            manager.get_last_update_timestamp()

        assert manager.query_api.query.call_count == 1


class TestSegmentUpdateTimestampRetry:
    """Test retry for get_segment_update_timestamp."""

    @pytest.mark.unit
    def test_retries_on_os_error(self, manager):
        """OSError should trigger retry."""
        manager.query_api.query.side_effect = OSError("network unreachable")

        with pytest.raises(OSError):
            manager.get_segment_update_timestamp(
                segment_id="seg1",
                measurement_name="segment_data",
                first_or_last="last",
            )

        assert manager.query_api.query.call_count == 3

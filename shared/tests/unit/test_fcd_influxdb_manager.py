"""Tests for FCDInfluxDBManager connection and retry logic."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from urllib3.util.retry import Retry

from idea_shared.classes.FCDInfluxDBManager import (
    DEFAULT_TIMEOUT_MS,
    FCDInfluxDBManager,
)


class TestFCDInfluxDBManagerInit:
    """Tests for FCDInfluxDBManager initialization."""

    def test_default_timeout_is_300_seconds(self):
        """Test default timeout is 300000ms (5 minutes)."""
        assert DEFAULT_TIMEOUT_MS == 300_000

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_initialization_with_default_timeout(self, mock_client_class):
        """Test manager initializes with default 300s timeout."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args.kwargs
        assert call_kwargs["timeout"] == DEFAULT_TIMEOUT_MS

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_initialization_with_custom_timeout(self, mock_client_class):
        """Test manager accepts custom timeout."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        custom_timeout = 30000
        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
            timeout=custom_timeout,
        )

        call_kwargs = mock_client_class.call_args.kwargs
        assert call_kwargs["timeout"] == custom_timeout

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_retry_strategy_includes_429_and_500_errors(self, mock_client_class):
        """Test retry strategy handles rate limiting and server errors."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        call_kwargs = mock_client_class.call_args.kwargs
        retries: Retry = call_kwargs["retries"]

        # Should retry on these status codes
        assert 429 in retries.status_forcelist  # Rate limiting
        assert 500 in retries.status_forcelist  # Internal server error
        assert 502 in retries.status_forcelist  # Bad gateway
        assert 503 in retries.status_forcelist  # Service unavailable
        assert 504 in retries.status_forcelist  # Gateway timeout

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_retry_strategy_has_backoff_jitter(self, mock_client_class):
        """Test retry strategy includes jitter for thundering herd prevention."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        call_kwargs = mock_client_class.call_args.kwargs
        retries: Retry = call_kwargs["retries"]

        # Should have jitter
        assert retries.backoff_jitter > 0

        manager.close()


class TestFCDInfluxDBManagerCheckConnection:
    """Tests for check_connection method."""

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_success(self, mock_client_class):
        """Test check_connection returns True when connection is active."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        result = manager.check_connection()

        assert result is True
        mock_client.ping.assert_called_once()

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_returns_false_on_ping_failure(self, mock_client_class):
        """Test check_connection returns False when ping fails."""
        mock_client = MagicMock()
        mock_client.ping.return_value = False
        mock_client.url = "http://localhost:8086"
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        result = manager.check_connection()

        assert result is False

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_handles_connection_error(self, mock_client_class):
        """Test check_connection handles ConnectionError gracefully."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionError("Connection refused")
        mock_client.url = "http://localhost:8086"
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        result = manager.check_connection()

        assert result is False

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_handles_timeout_error(self, mock_client_class):
        """Test check_connection handles TimeoutError gracefully."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = TimeoutError("Connection timed out")
        mock_client.url = "http://localhost:8086"
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        result = manager.check_connection()

        assert result is False

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_handles_os_error(self, mock_client_class):
        """Test check_connection handles OSError (network issues) gracefully."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = OSError("Network unreachable")
        mock_client.url = "http://localhost:8086"
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        result = manager.check_connection()

        assert result is False

        manager.close()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_check_connection_returns_false_when_client_not_initialized(
        self, mock_client_class
    ):
        """Test check_connection returns False when client is None."""
        mock_client_class.return_value = MagicMock()

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        # Simulate client being None
        manager.client = None

        result = manager.check_connection()

        assert result is False


class TestFCDInfluxDBManagerContextManager:
    """Tests for context manager (with statement) usage."""

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_context_manager_closes_connection(self, mock_client_class):
        """Test context manager properly closes connection on exit."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        ) as _:
            # Use manager
            pass

        mock_client.close.assert_called_once()

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_context_manager_closes_on_exception(self, mock_client_class):
        """Test context manager closes connection even when exception occurs."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with pytest.raises(ValueError):
            with FCDInfluxDBManager(
                url="http://localhost:8086",
                token="test-token",
                org="test-org",
                bucket="test-bucket",
            ) as _:
                raise ValueError("Test exception")

        mock_client.close.assert_called_once()


class TestFCDInfluxDBManagerInitializationErrors:
    """Tests for initialization error handling."""

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_initialization_handles_connection_error(self, mock_client_class):
        """Test initialization handles ConnectionError."""
        mock_client_class.side_effect = ConnectionError("Cannot connect")

        with pytest.raises(ConnectionError):
            FCDInfluxDBManager(
                url="http://localhost:8086",
                token="test-token",
                org="test-org",
                bucket="test-bucket",
            )

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_initialization_handles_timeout_error(self, mock_client_class):
        """Test initialization handles TimeoutError."""
        mock_client_class.side_effect = TimeoutError("Connection timed out")

        with pytest.raises(TimeoutError):
            FCDInfluxDBManager(
                url="http://localhost:8086",
                token="test-token",
                org="test-org",
                bucket="test-bucket",
            )

    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_initialization_handles_os_error(self, mock_client_class):
        """Test initialization handles OSError."""
        mock_client_class.side_effect = OSError("Network unreachable")

        with pytest.raises(OSError):
            FCDInfluxDBManager(
                url="http://localhost:8086",
                token="test-token",
                org="test-org",
                bucket="test-bucket",
            )


class TestGetSegmentDataDataframe:
    """Tests for get_segment_data_dataframe method."""

    @pytest.mark.unit
    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_query_fields_list_is_not_mutated(self, mock_client_class):
        """Regression test: query_fields must not be mutated across calls (issue #237)."""
        mock_client = MagicMock()
        mock_query_api = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        # Return a DataFrame that has _time + the requested fields
        mock_df = pd.DataFrame(
            {"_time": ["2024-01-01"], "speed": [50.0], "confidence": [0.9]}
        )
        mock_query_api.query_data_frame.return_value = mock_df

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        query_fields = ["speed", "confidence"]
        original_fields = list(query_fields)

        # Call twice with the same list reference
        manager.get_segment_data_dataframe(
            segment_id="seg-1",
            measurement_name="segment_data",
            query_fields=query_fields,
        )
        manager.get_segment_data_dataframe(
            segment_id="seg-1",
            measurement_name="segment_data",
            query_fields=query_fields,
        )

        # The caller's list must be unchanged
        assert query_fields == original_fields

        manager.close()

    @pytest.mark.unit
    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_empty_range_returns_none_without_querying(self, mock_client_class):
        """When start_time == end_time, should return None without hitting InfluxDB.

        Regression test for: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/315
        InfluxDB returns HTTP 400 'cannot query an empty range' when start == stop.
        """
        from datetime import UTC, datetime

        mock_client = MagicMock()
        mock_query_api = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        ts = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        result = manager.get_segment_data_dataframe(
            segment_id="seg-1",
            measurement_name="segment_data",
            start_time=ts,
            end_time=ts,
        )

        assert result is None
        mock_query_api.query_data_frame.assert_not_called()

        manager.close()

    @pytest.mark.unit
    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_start_after_end_returns_none_without_querying(self, mock_client_class):
        """When start_time > end_time, should return None without hitting InfluxDB."""
        from datetime import UTC, datetime, timedelta

        mock_client = MagicMock()
        mock_query_api = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        now = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        result = manager.get_segment_data_dataframe(
            segment_id="seg-1",
            measurement_name="segment_data",
            start_time=now,
            end_time=now - timedelta(minutes=5),
        )

        assert result is None
        mock_query_api.query_data_frame.assert_not_called()

        manager.close()


class TestGetSegmentDataCsv:
    """Tests for get_segment_data_csv method."""

    @pytest.mark.unit
    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_empty_range_returns_none_without_querying(self, mock_client_class):
        """When start_time == end_time, get_segment_data_csv should return None.

        Regression test for: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/315
        """
        from datetime import UTC, datetime

        mock_client = MagicMock()
        mock_query_api = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        ts = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        result = manager.get_segment_data_csv(
            segment_id="seg-1",
            measurement_name="segment_data",
            start_time=ts,
            end_time=ts,
        )

        assert result is None
        mock_query_api.query_csv.assert_not_called()

        manager.close()

    @pytest.mark.unit
    @patch("idea_shared.classes.FCDInfluxDBManager.InfluxDBClient")
    def test_start_after_end_returns_none_without_querying(self, mock_client_class):
        """When start_time > end_time, get_segment_data_csv should return None."""
        from datetime import UTC, datetime, timedelta

        mock_client = MagicMock()
        mock_query_api = MagicMock()
        mock_client.query_api.return_value = mock_query_api
        mock_client_class.return_value = mock_client

        manager = FCDInfluxDBManager(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )

        now = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        result = manager.get_segment_data_csv(
            segment_id="seg-1",
            measurement_name="segment_data",
            start_time=now,
            end_time=now - timedelta(minutes=5),
        )

        assert result is None
        mock_query_api.query_csv.assert_not_called()

        manager.close()

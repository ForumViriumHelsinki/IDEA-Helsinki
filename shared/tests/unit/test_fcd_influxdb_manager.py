"""Tests for FCDInfluxDBManager connection and retry logic."""

from unittest.mock import MagicMock, patch

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
        ) as manager:
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
            ) as manager:
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

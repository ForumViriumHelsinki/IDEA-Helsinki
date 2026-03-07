"""Tests for shared observability module."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestConfigureSentry:
    """Tests for configure_sentry function."""

    @patch.dict("os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"})
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_initializes_sentry_when_dsn_set(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_called_once()
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["dsn"] == "https://key@sentry.io/123"
        assert call_kwargs["environment"] == "test"
        assert call_kwargs["sample_rate"] == 0.1

    @patch.dict("os.environ", {"SENTRY_DSN": ""}, clear=False)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_skips_sentry_when_dsn_empty(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_skips_sentry_when_dsn_not_set(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_not_called()

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "  https://key@sentry.io/123  ", "ENVIRONMENT": "staging"}
    )
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_strips_whitespace_from_dsn(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_called_once()
        assert mock_sentry.init.call_args[1]["dsn"] == "https://key@sentry.io/123"

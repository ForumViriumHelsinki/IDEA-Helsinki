"""Tests for shared observability module."""

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestDetectRelease:
    """Tests for _detect_release function."""

    @patch.dict("os.environ", {"SENTRY_RELEASE": "idea-helsinki@1.2.3"}, clear=False)
    def test_prefers_sentry_release_env_var(self):
        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() == "idea-helsinki@1.2.3"

    @patch.dict("os.environ", {"SENTRY_RELEASE": "  custom@2.0.0  "}, clear=False)
    def test_strips_whitespace_from_env_var(self):
        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() == "custom@2.0.0"

    @patch.dict("os.environ", {}, clear=True)
    @patch("idea_shared.observability.sentry.VERSION_FILE")
    def test_falls_back_to_version_file(self, mock_path):
        mock_path.is_file.return_value = True
        mock_path.read_text.return_value = "0.18.1\n"

        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() == "idea-helsinki@0.18.1"

    @patch.dict("os.environ", {}, clear=True)
    @patch("idea_shared.observability.sentry.VERSION_FILE")
    def test_returns_none_when_no_source(self, mock_path):
        mock_path.is_file.return_value = False

        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() is None

    @patch.dict("os.environ", {"SENTRY_RELEASE": ""}, clear=False)
    @patch("idea_shared.observability.sentry.VERSION_FILE")
    def test_empty_env_falls_back_to_version_file(self, mock_path):
        mock_path.is_file.return_value = True
        mock_path.read_text.return_value = "0.18.1"

        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() == "idea-helsinki@0.18.1"

    @patch.dict("os.environ", {"SENTRY_RELEASE": "explicit@9.9.9"}, clear=False)
    @patch("idea_shared.observability.sentry.VERSION_FILE")
    def test_env_var_takes_precedence_over_version_file(self, mock_path):
        mock_path.is_file.return_value = True
        mock_path.read_text.return_value = "0.18.1"

        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() == "explicit@9.9.9"

    @patch.dict("os.environ", {}, clear=True)
    @patch("idea_shared.observability.sentry.VERSION_FILE")
    def test_returns_none_on_version_file_read_error(self, mock_path):
        mock_path.is_file.side_effect = OSError("Permission denied")

        from idea_shared.observability.sentry import _detect_release

        assert _detect_release() is None


@pytest.mark.unit
class TestConfigureSentry:
    """Tests for configure_sentry function."""

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"}
    )
    @patch(
        "idea_shared.observability.sentry._detect_release",
        return_value="idea-helsinki@1.0.0",
    )
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_initializes_sentry_when_dsn_set(self, mock_sentry, _mock_detect_release):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_called_once()
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["dsn"] == "https://key@sentry.io/123"
        assert call_kwargs["environment"] == "test"
        assert call_kwargs["release"] == "idea-helsinki@1.0.0"
        assert call_kwargs["sample_rate"] == 0.1

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"}
    )
    @patch(
        "idea_shared.observability.sentry._detect_release",
        return_value="idea-helsinki@1.0.0",
    )
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_sets_service_tag_after_init(self, mock_sentry, _mock_detect_release):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("orchestrator")
        mock_sentry.set_tag.assert_called_once_with("service", "orchestrator")

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"}
    )
    @patch("idea_shared.observability.sentry._detect_release", return_value=None)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_sets_service_tag_for_each_service(self, mock_sentry, _mock_detect_release):
        from idea_shared.observability.sentry import configure_sentry

        for service in ("orchestrator", "traffic-monitor", "fcd-manager"):
            mock_sentry.reset_mock()
            configure_sentry(service)
            mock_sentry.set_tag.assert_called_once_with("service", service)

    @patch.dict("os.environ", {"SENTRY_DSN": ""}, clear=False)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_skips_sentry_when_dsn_empty(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_not_called()
        mock_sentry.set_tag.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_skips_sentry_when_dsn_not_set(self, mock_sentry):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_not_called()
        mock_sentry.set_tag.assert_not_called()

    @patch.dict(
        "os.environ",
        {"SENTRY_DSN": "  https://key@sentry.io/123  ", "ENVIRONMENT": "staging"},
    )
    @patch("idea_shared.observability.sentry._detect_release", return_value=None)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_strips_whitespace_from_dsn(self, mock_sentry, _mock_detect_release):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        mock_sentry.init.assert_called_once()
        assert mock_sentry.init.call_args[1]["dsn"] == "https://key@sentry.io/123"

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"}
    )
    @patch("idea_shared.observability.sentry._detect_release", return_value=None)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_passes_none_release_when_not_detected(
        self, mock_sentry, _mock_detect_release
    ):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        assert mock_sentry.init.call_args[1]["release"] is None

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
class TestGetSampleRateFromEnv:
    """Tests for the _get_sample_rate_from_env helper."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_default_when_env_var_absent(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.5

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "0.3"}, clear=False)
    def test_parses_valid_float(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.3

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "0.0"}, clear=False)
    def test_accepts_lower_bound(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.0

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "1.0"}, clear=False)
    def test_accepts_upper_bound(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 1.0

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "1.5"}, clear=False)
    def test_rejects_value_above_1(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.5

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "-0.1"}, clear=False)
    def test_rejects_negative_value(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.5

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "not-a-float"}, clear=False)
    def test_rejects_non_numeric_value(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.5

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "  0.7  "}, clear=False)
    def test_strips_whitespace(self):
        from idea_shared.observability.sentry import _get_sample_rate_from_env

        assert _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 0.5) == 0.7


@pytest.mark.unit
class TestGetSampleRate:
    """Tests for _get_sample_rate function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_default_1_0(self):
        from idea_shared.observability.sentry import _get_sample_rate

        assert _get_sample_rate() == 1.0

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "0.5"}, clear=False)
    def test_reads_from_env_var(self):
        from idea_shared.observability.sentry import _get_sample_rate

        assert _get_sample_rate() == 0.5

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "not-a-number"}, clear=False)
    def test_falls_back_to_default_on_invalid_value(self):
        from idea_shared.observability.sentry import _get_sample_rate

        assert _get_sample_rate() == 1.0

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "  0.25  "}, clear=False)
    def test_strips_whitespace(self):
        from idea_shared.observability.sentry import _get_sample_rate

        assert _get_sample_rate() == 0.25

    @patch.dict("os.environ", {"SENTRY_SAMPLE_RATE": "1.5"}, clear=False)
    def test_rejects_out_of_range_value(self):
        from idea_shared.observability.sentry import _get_sample_rate

        assert _get_sample_rate() == 1.0


@pytest.mark.unit
class TestGetTracesSampleRate:
    """Tests for _get_traces_sample_rate function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_default_0_1(self):
        from idea_shared.observability.sentry import _get_traces_sample_rate

        assert _get_traces_sample_rate() == 0.1

    @patch.dict("os.environ", {"SENTRY_TRACES_SAMPLE_RATE": "0.2"}, clear=False)
    def test_reads_from_env_var(self):
        from idea_shared.observability.sentry import _get_traces_sample_rate

        assert _get_traces_sample_rate() == 0.2

    @patch.dict("os.environ", {"SENTRY_TRACES_SAMPLE_RATE": "bad-value"}, clear=False)
    def test_falls_back_to_default_on_invalid_value(self):
        from idea_shared.observability.sentry import _get_traces_sample_rate

        assert _get_traces_sample_rate() == 0.1

    @patch.dict("os.environ", {"SENTRY_TRACES_SAMPLE_RATE": "1.0"}, clear=False)
    def test_allows_full_sampling(self):
        from idea_shared.observability.sentry import _get_traces_sample_rate

        assert _get_traces_sample_rate() == 1.0

    @patch.dict("os.environ", {"SENTRY_TRACES_SAMPLE_RATE": "2.0"}, clear=False)
    def test_rejects_out_of_range_value(self):
        from idea_shared.observability.sentry import _get_traces_sample_rate

        assert _get_traces_sample_rate() == 0.1


@pytest.mark.unit
class TestGetProfilesSampleRate:
    """Tests for _get_profiles_sample_rate function."""

    @patch.dict("os.environ", {}, clear=True)
    def test_returns_default_0_1(self):
        from idea_shared.observability.sentry import _get_profiles_sample_rate

        assert _get_profiles_sample_rate() == 0.1

    @patch.dict("os.environ", {"SENTRY_PROFILES_SAMPLE_RATE": "0.05"}, clear=False)
    def test_reads_from_env_var(self):
        from idea_shared.observability.sentry import _get_profiles_sample_rate

        assert _get_profiles_sample_rate() == 0.05

    @patch.dict("os.environ", {"SENTRY_PROFILES_SAMPLE_RATE": "bad-value"}, clear=False)
    def test_falls_back_to_default_on_invalid_value(self):
        from idea_shared.observability.sentry import _get_profiles_sample_rate

        assert _get_profiles_sample_rate() == 0.1

    @patch.dict("os.environ", {"SENTRY_PROFILES_SAMPLE_RATE": "0.0"}, clear=False)
    def test_allows_zero_sampling(self):
        from idea_shared.observability.sentry import _get_profiles_sample_rate

        assert _get_profiles_sample_rate() == 0.0

    @patch.dict("os.environ", {"SENTRY_PROFILES_SAMPLE_RATE": "-1.0"}, clear=False)
    def test_rejects_negative_value(self):
        from idea_shared.observability.sentry import _get_profiles_sample_rate

        assert _get_profiles_sample_rate() == 0.1


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
        # Default: capture all errors (1.0), sample traces/profiles (0.1)
        assert call_kwargs["sample_rate"] == 1.0
        assert call_kwargs["traces_sample_rate"] == 0.1
        assert call_kwargs["profiles_sample_rate"] == 0.1

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

    @patch.dict(
        "os.environ",
        {
            "SENTRY_DSN": "https://key@sentry.io/123",
            "ENVIRONMENT": "production",
            "SENTRY_SAMPLE_RATE": "0.5",
            "SENTRY_TRACES_SAMPLE_RATE": "0.2",
            "SENTRY_PROFILES_SAMPLE_RATE": "0.05",
        },
    )
    @patch("idea_shared.observability.sentry._detect_release", return_value=None)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_uses_env_var_overrides_for_sampling_rates(
        self, mock_sentry, _mock_detect_release
    ):
        from idea_shared.observability.sentry import configure_sentry

        configure_sentry("test-service")
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["sample_rate"] == 0.5
        assert call_kwargs["traces_sample_rate"] == 0.2
        assert call_kwargs["profiles_sample_rate"] == 0.05

    @patch.dict(
        "os.environ", {"SENTRY_DSN": "https://key@sentry.io/123", "ENVIRONMENT": "test"}
    )
    @patch("idea_shared.observability.sentry._detect_release", return_value=None)
    @patch("idea_shared.observability.sentry.sentry_sdk")
    def test_passes_before_breadcrumb_filter(self, mock_sentry, _mock_detect_release):
        from idea_shared.observability.sentry import (
            _filter_breadcrumb,
            configure_sentry,
        )

        configure_sentry("test-service")
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["before_breadcrumb"] is _filter_breadcrumb


@pytest.mark.unit
class TestFilterBreadcrumb:
    """Tests for _filter_breadcrumb callback."""

    def test_drops_successful_influxdb_write(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/api/v2/write",
                "http.response.status_code": 204,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is None

    def test_drops_successful_influxdb_ping(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/ping",
                "http.response.status_code": 204,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is None

    def test_drops_successful_influxdb_query(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/api/v2/query",
                "http.response.status_code": 200,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is None

    def test_drops_localhost_influxdb_breadcrumb(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://localhost:8086/ping",
                "http.response.status_code": 200,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is None

    def test_keeps_failed_influxdb_request(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/api/v2/write",
                "http.response.status_code": 500,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_influxdb_client_error(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/api/v2/query",
                "http.response.status_code": 401,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_external_api_breadcrumb(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "https://kartta.hel.fi/ws/geoserver/avoindata/wfs",
                "http.response.status_code": 200,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_non_httplib_breadcrumb(self):
        breadcrumb = {
            "category": "logging",
            "level": "warning",
            "message": "Something happened",
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_warning_level_influxdb_breadcrumb(self):
        breadcrumb = {
            "category": "httplib",
            "level": "warning",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/api/v2/write",
                "http.response.status_code": 200,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_breadcrumb_with_missing_data(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_breadcrumb_with_missing_url(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {"http.response.status_code": 200},
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_breadcrumb_with_missing_status_code(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {"url": "http://idea-helsinki-influxdb-helm-webapp:8086/ping"},
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_breadcrumb_with_string_status_code(self):
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://idea-helsinki-influxdb-helm-webapp:8086/ping",
                "http.response.status_code": "200",
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_keeps_breadcrumb_with_none_url(self):
        """Explicitly None URL (key present but set to None) should not crash."""
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": None,
                "http.response.status_code": 200,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is breadcrumb

    def test_drops_influxdb_breadcrumb_with_mixed_case_url(self):
        """URL matching is case-insensitive (hostnames are case-insensitive by RFC)."""
        breadcrumb = {
            "category": "httplib",
            "level": "info",
            "data": {
                "url": "http://INFLUXDB-service:8086/api/v2/write",
                "http.response.status_code": 204,
            },
        }
        from idea_shared.observability.sentry import _filter_breadcrumb

        assert _filter_breadcrumb(breadcrumb, {}) is None

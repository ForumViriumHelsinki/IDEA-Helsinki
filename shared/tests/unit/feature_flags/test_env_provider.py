"""Unit tests for environment variable feature flag provider."""

import os

import pytest

from idea_shared.feature_flags.providers import EnvironmentVariableProvider


class TestEnvironmentVariableProvider:
    """Tests for EnvironmentVariableProvider."""

    @pytest.mark.unit
    def test_boolean_flag_true_variations(self):
        """Boolean flag recognizes various true values."""
        provider = EnvironmentVariableProvider()
        true_values = ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]

        for value in true_values:
            os.environ["FEATURE_FLAG_TEST"] = value
            try:
                result = provider.resolve_boolean_details("test", default_value=False)
                assert result.value is True, f"Failed for value: {value}"
                assert result.variant == "enabled"
            finally:
                del os.environ["FEATURE_FLAG_TEST"]

    @pytest.mark.unit
    def test_boolean_flag_false_variations(self):
        """Boolean flag recognizes various false values."""
        provider = EnvironmentVariableProvider()
        false_values = ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]

        for value in false_values:
            os.environ["FEATURE_FLAG_TEST"] = value
            try:
                result = provider.resolve_boolean_details("test", default_value=True)
                assert result.value is False, f"Failed for value: {value}"
                assert result.variant == "disabled"
            finally:
                del os.environ["FEATURE_FLAG_TEST"]

    @pytest.mark.unit
    def test_boolean_flag_missing_uses_default(self):
        """Missing boolean flag uses default value."""
        provider = EnvironmentVariableProvider()

        # Ensure env var is not set
        if "FEATURE_FLAG_MISSING" in os.environ:
            del os.environ["FEATURE_FLAG_MISSING"]

        result = provider.resolve_boolean_details("missing", default_value=True)
        assert result.value is True
        assert result.reason == "DEFAULT"

    @pytest.mark.unit
    def test_string_flag(self):
        """String flag resolves correctly."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_LOG_LEVEL"] = "debug"

        try:
            result = provider.resolve_string_details("log_level", default_value="info")
            assert result.value == "debug"
            assert result.reason == "STATIC"
        finally:
            del os.environ["FEATURE_FLAG_LOG_LEVEL"]

    @pytest.mark.unit
    def test_integer_flag(self):
        """Integer flag resolves correctly."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_MAX_CONNECTIONS"] = "100"

        try:
            result = provider.resolve_integer_details(
                "max_connections", default_value=10
            )
            assert result.value == 100
            assert result.reason == "STATIC"
        finally:
            del os.environ["FEATURE_FLAG_MAX_CONNECTIONS"]

    @pytest.mark.unit
    def test_integer_flag_invalid_value(self):
        """Invalid integer value uses default."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_MAX_CONNECTIONS"] = "not_a_number"

        try:
            result = provider.resolve_integer_details(
                "max_connections", default_value=10
            )
            assert result.value == 10
            assert result.reason == "ERROR"
        finally:
            del os.environ["FEATURE_FLAG_MAX_CONNECTIONS"]

    @pytest.mark.unit
    def test_float_flag(self):
        """Float flag resolves correctly."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_THRESHOLD"] = "0.75"

        try:
            result = provider.resolve_float_details("threshold", default_value=0.5)
            assert result.value == 0.75
            assert result.reason == "STATIC"
        finally:
            del os.environ["FEATURE_FLAG_THRESHOLD"]

    @pytest.mark.unit
    def test_float_flag_invalid_value(self):
        """Invalid float value uses default."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_THRESHOLD"] = "invalid"

        try:
            result = provider.resolve_float_details("threshold", default_value=0.5)
            assert result.value == 0.5
            assert result.reason == "ERROR"
        finally:
            del os.environ["FEATURE_FLAG_THRESHOLD"]

    @pytest.mark.unit
    def test_object_flag_json(self):
        """Object flag parses JSON correctly."""
        import json

        provider = EnvironmentVariableProvider()
        config = {"key1": "value1", "key2": 42}
        os.environ["FEATURE_FLAG_CONFIG"] = json.dumps(config)

        try:
            result = provider.resolve_object_details("config", default_value={})
            assert result.value == config
            assert result.reason == "STATIC"
        finally:
            del os.environ["FEATURE_FLAG_CONFIG"]

    @pytest.mark.unit
    def test_object_flag_invalid_json(self):
        """Invalid JSON object uses default."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_CONFIG"] = "not valid json"

        try:
            default = {"default": "config"}
            result = provider.resolve_object_details("config", default_value=default)
            assert result.value == default
            assert result.reason == "ERROR"
        finally:
            del os.environ["FEATURE_FLAG_CONFIG"]

    @pytest.mark.unit
    def test_object_flag_non_dict_json(self):
        """JSON that's not a dict uses default."""
        import json

        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_CONFIG"] = json.dumps(["not", "a", "dict"])

        try:
            default = {"default": "config"}
            result = provider.resolve_object_details("config", default_value=default)
            assert result.value == default
            assert result.reason == "ERROR"
        finally:
            del os.environ["FEATURE_FLAG_CONFIG"]

    @pytest.mark.unit
    def test_custom_prefix(self):
        """Provider can use custom environment variable prefix."""
        provider = EnvironmentVariableProvider(prefix="CUSTOM_")
        os.environ["CUSTOM_TEST_FLAG"] = "true"

        try:
            result = provider.resolve_boolean_details("test_flag", default_value=False)
            assert result.value is True
        finally:
            del os.environ["CUSTOM_TEST_FLAG"]

    @pytest.mark.unit
    def test_flag_name_case_insensitive(self):
        """Flag names are case-insensitive for env vars."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_TEST_FLAG"] = "true"

        try:
            # Should work with different cases
            result1 = provider.resolve_boolean_details("test_flag", default_value=False)
            result2 = provider.resolve_boolean_details("TEST_FLAG", default_value=False)
            assert result1.value is True
            assert result2.value is True
        finally:
            del os.environ["FEATURE_FLAG_TEST_FLAG"]

    @pytest.mark.unit
    def test_provider_metadata(self):
        """Provider returns correct metadata."""
        provider = EnvironmentVariableProvider()
        metadata = provider.get_metadata()
        assert metadata.name == "EnvironmentVariableProvider"

    @pytest.mark.unit
    def test_multiple_flags(self):
        """Provider handles multiple environment variables."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_FEATURE_A"] = "true"
        os.environ["FEATURE_FLAG_FEATURE_B"] = "false"
        os.environ["FEATURE_FLAG_MAX_RETRY"] = "3"

        try:
            result_a = provider.resolve_boolean_details("feature_a", False)
            assert result_a.value is True

            result_b = provider.resolve_boolean_details("feature_b", True)
            assert result_b.value is False

            result_retry = provider.resolve_integer_details("max_retry", 1)
            assert result_retry.value == 3
        finally:
            del os.environ["FEATURE_FLAG_FEATURE_A"]
            del os.environ["FEATURE_FLAG_FEATURE_B"]
            del os.environ["FEATURE_FLAG_MAX_RETRY"]

    @pytest.mark.unit
    def test_negative_integer(self):
        """Negative integers are parsed correctly."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_OFFSET"] = "-10"

        try:
            result = provider.resolve_integer_details("offset", default_value=0)
            assert result.value == -10
        finally:
            del os.environ["FEATURE_FLAG_OFFSET"]

    @pytest.mark.unit
    def test_negative_float(self):
        """Negative floats are parsed correctly."""
        provider = EnvironmentVariableProvider()
        os.environ["FEATURE_FLAG_TEMP"] = "-273.15"

        try:
            result = provider.resolve_float_details("temp", default_value=0.0)
            assert result.value == -273.15
        finally:
            del os.environ["FEATURE_FLAG_TEMP"]

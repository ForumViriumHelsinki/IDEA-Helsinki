"""Unit tests for JSON file feature flag provider."""

import json
import tempfile
from pathlib import Path

import pytest

from idea_shared.feature_flags.providers import JsonFileProvider


class TestJsonFileProvider:
    """Tests for JsonFileProvider."""

    @pytest.mark.unit
    def test_nonexistent_file_uses_defaults(self):
        """Provider handles nonexistent file gracefully."""
        provider = JsonFileProvider("/nonexistent/feature_flags.json")

        # Should use default value
        result = provider.resolve_boolean_details("some_flag", default_value=True)
        assert result.value is True
        assert result.reason == "DEFAULT"

    @pytest.mark.unit
    def test_empty_json_file(self):
        """Provider handles empty JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_boolean_details("flag", default_value=False)
            assert result.value is False
            assert result.reason == "DEFAULT"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_boolean_flag_enabled(self):
        """Boolean flag resolves to enabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"test_flag": {"enabled": True}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_boolean_details("test_flag", default_value=False)
            assert result.value is True
            assert result.reason == "STATIC"
            assert result.variant == "enabled"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_boolean_flag_disabled(self):
        """Boolean flag resolves to disabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"test_flag": {"enabled": False}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_boolean_details("test_flag", default_value=True)
            assert result.value is False
            assert result.reason == "STATIC"
            assert result.variant == "disabled"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_string_flag(self):
        """String flag resolves correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"log_level": {"value": "debug"}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_string_details("log_level", default_value="info")
            assert result.value == "debug"
            assert result.reason == "STATIC"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_integer_flag(self):
        """Integer flag resolves correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"max_connections": {"value": 100}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_integer_details(
                "max_connections", default_value=10
            )
            assert result.value == 100
            assert result.reason == "STATIC"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_integer_with_string_value(self):
        """Integer flag handles string values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"max_connections": {"value": "50"}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_integer_details(
                "max_connections", default_value=10
            )
            assert result.value == 50
            assert result.reason == "STATIC"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_integer_invalid_value_uses_default(self):
        """Invalid integer value falls back to default."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"max_connections": {"value": "invalid"}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_integer_details(
                "max_connections", default_value=10
            )
            assert result.value == 10
            assert result.reason == "ERROR"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_float_flag(self):
        """Float flag resolves correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"threshold": {"value": 0.75}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_float_details("threshold", default_value=0.5)
            assert result.value == 0.75
            assert result.reason == "STATIC"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_object_flag(self):
        """Object/dict flag resolves correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"config": {"value": {"key1": "value1", "key2": 42}}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_object_details("config", default_value={})
            assert result.value == {"key1": "value1", "key2": 42}
            assert result.reason == "STATIC"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_resolve_object_invalid_type_uses_default(self):
        """Object flag with non-dict value uses default."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {"flags": {"config": {"value": "not a dict"}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            default = {"default": "config"}
            result = provider.resolve_object_details("config", default_value=default)
            assert result.value == default
            assert result.reason == "ERROR"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_multiple_flags_in_same_file(self):
        """Provider handles multiple flags correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {
                "flags": {
                    "feature_a": {"enabled": True},
                    "feature_b": {"enabled": False},
                    "max_retry": {"value": 3},
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)

            result_a = provider.resolve_boolean_details("feature_a", False)
            assert result_a.value is True

            result_b = provider.resolve_boolean_details("feature_b", True)
            assert result_b.value is False

            result_retry = provider.resolve_integer_details("max_retry", 1)
            assert result_retry.value == 3
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_provider_metadata(self):
        """Provider returns correct metadata."""
        provider = JsonFileProvider("/tmp/test.json")
        metadata = provider.get_metadata()
        assert metadata.name == "JsonFileProvider"

    @pytest.mark.unit
    def test_invalid_json_file(self):
        """Provider handles invalid JSON gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content {")
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            # Should use default since file couldn't be parsed
            result = provider.resolve_boolean_details("flag", default_value=True)
            assert result.value is True
            assert result.reason == "DEFAULT"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_flag_with_description(self):
        """Flags can include optional description field."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {
                "flags": {
                    "feature": {
                        "enabled": True,
                        "description": "This is a test feature",
                    }
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            result = provider.resolve_boolean_details("feature", False)
            # Description is informational only, doesn't affect resolution
            assert result.value is True
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_invalid_json_root_not_dict(self):
        """Provider handles invalid JSON where root is not a dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write JSON array instead of object
            json.dump(["invalid", "root", "type"], f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            # Should fall back to default value
            result = provider.resolve_boolean_details("test_flag", default_value=True)
            assert result.value is True
            assert result.reason == "DEFAULT"
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_invalid_json_flags_not_dict(self):
        """Provider handles invalid JSON where 'flags' is not a dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            # Write flags as array instead of object
            data = {"flags": ["invalid", "flags", "type"]}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            # Should fall back to default value
            result = provider.resolve_boolean_details("test_flag", default_value=False)
            assert result.value is False
            assert result.reason == "DEFAULT"
        finally:
            Path(filepath).unlink()

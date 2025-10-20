"""Unit tests for feature flag manager."""

import json
import tempfile
from pathlib import Path

import pytest

from idea_shared.feature_flags import (
    FeatureFlag,
    FeatureFlagManager,
    get_feature_flags,
    initialize_feature_flags,
)
from idea_shared.feature_flags.providers import JsonFileProvider


class TestFeatureFlagManager:
    """Tests for FeatureFlagManager."""

    @pytest.fixture
    def temp_flags_file(self):
        """Create a temporary feature flags JSON file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {
                "flags": {
                    "enable_caching": {"enabled": True},
                    "max_connections": {"value": 50},
                    "log_level": {"value": "debug"},
                    "config": {"value": {"key": "value"}},
                }
            }
            json.dump(data, f)
            filepath = f.name

        yield filepath

        Path(filepath).unlink()

    @pytest.mark.unit
    def test_manager_initialization(self, temp_flags_file):
        """Manager initializes with provider."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)
        assert manager is not None

    @pytest.mark.unit
    def test_is_enabled_with_feature_flag_enum(self, temp_flags_file):
        """is_enabled works with FeatureFlag enum."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        # Using FeatureFlag enum (with default since it won't be in file)
        result = manager.is_enabled(
            FeatureFlag.ENABLE_PARALLEL_PROCESSING
        )
        # Should use the default from FlagDefaults (True)
        assert result is True

    @pytest.mark.unit
    def test_is_enabled_with_string(self, temp_flags_file):
        """is_enabled works with string flag names."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.is_enabled("enable_caching", default=False)
        assert result is True

    @pytest.mark.unit
    def test_is_enabled_missing_flag_uses_default(self, temp_flags_file):
        """Missing flag uses provided default."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.is_enabled("nonexistent_flag", default=True)
        assert result is True

        result = manager.is_enabled("nonexistent_flag", default=False)
        assert result is False

    @pytest.mark.unit
    def test_get_string(self, temp_flags_file):
        """get_string retrieves string values."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.get_string("log_level", default="info")
        assert result == "debug"

    @pytest.mark.unit
    def test_get_string_missing_uses_default(self, temp_flags_file):
        """get_string uses default for missing flags."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.get_string("missing_string", default="default_value")
        assert result == "default_value"

    @pytest.mark.unit
    def test_get_int(self, temp_flags_file):
        """get_int retrieves integer values."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.get_int("max_connections", default=10)
        assert result == 50

    @pytest.mark.unit
    def test_get_int_missing_uses_default(self, temp_flags_file):
        """get_int uses default for missing flags."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.get_int("missing_int", default=42)
        assert result == 42

    @pytest.mark.unit
    def test_get_float(self, temp_flags_file):
        """get_float retrieves float values."""
        # Create a file with a float value
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {"flags": {"threshold": {"value": 0.75}}}
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            manager = FeatureFlagManager(provider)

            result = manager.get_float("threshold", default=0.5)
            assert result == 0.75
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_get_object(self, temp_flags_file):
        """get_object retrieves dict values."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        result = manager.get_object("config", default={})
        assert result == {"key": "value"}

    @pytest.mark.unit
    def test_get_object_missing_uses_default(self, temp_flags_file):
        """get_object uses default for missing flags."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider)

        default = {"default": "config"}
        result = manager.get_object("missing_object", default=default)
        assert result == default

    @pytest.mark.unit
    def test_custom_domain(self, temp_flags_file):
        """Manager can use custom domain name."""
        provider = JsonFileProvider(temp_flags_file)
        manager = FeatureFlagManager(provider, domain="custom-domain")

        result = manager.is_enabled("enable_caching", default=False)
        assert result is True


class TestGlobalManager:
    """Tests for global manager singleton."""

    @pytest.fixture(autouse=True)
    def reset_global_manager(self):
        """Reset global manager before each test."""
        import idea_shared.feature_flags.manager as manager_module

        manager_module._global_manager = None
        yield
        manager_module._global_manager = None

    @pytest.mark.unit
    def test_initialize_feature_flags(self):
        """initialize_feature_flags creates global instance."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"flags": {}}, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            manager = initialize_feature_flags(provider)

            assert manager is not None
            assert isinstance(manager, FeatureFlagManager)
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_get_feature_flags_after_initialization(self):
        """get_feature_flags returns initialized instance."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"flags": {}}, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            manager1 = initialize_feature_flags(provider)
            manager2 = get_feature_flags()

            assert manager1 is manager2
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_get_feature_flags_not_initialized_raises(self):
        """get_feature_flags raises if not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            get_feature_flags()

    @pytest.mark.unit
    def test_reinitialize_replaces_global_instance(self):
        """Calling initialize_feature_flags twice replaces instance."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"flags": {}}, f)
            filepath = f.name

        try:
            provider1 = JsonFileProvider(filepath)
            manager1 = initialize_feature_flags(provider1)

            provider2 = JsonFileProvider(filepath)
            manager2 = initialize_feature_flags(provider2)

            # Should be different instances
            assert manager1 is not manager2

            # get_feature_flags should return the new one
            current = get_feature_flags()
            assert current is manager2
        finally:
            Path(filepath).unlink()

    @pytest.mark.unit
    def test_get_all_flags_returns_empty_dict(self):
        """get_all_flags returns empty dict (not implemented)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"flags": {}}, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            manager = FeatureFlagManager(provider)

            result = manager.get_all_flags()
            assert result == {}
        finally:
            Path(filepath).unlink()

"""Integration tests for feature flag providers.

These tests verify real-world usage patterns and provider switching.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from idea_shared.feature_flags import (
    FeatureFlag,
    get_feature_flags,
    initialize_feature_flags,
)
from idea_shared.feature_flags.providers import (
    EnvironmentVariableProvider,
    JsonFileProvider,
)


class TestProviderIntegration:
    """Integration tests for feature flag providers."""

    @pytest.mark.integration
    def test_json_provider_to_env_provider_switch(self):
        """Test switching from JSON to environment variable provider."""
        import idea_shared.feature_flags.manager as manager_module

        # Reset global state
        manager_module._global_manager = None

        # Start with JSON provider
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {
                "flags": {
                    "enable_parallel_processing": {"enabled": False},
                    "enable_segment_caching": {"enabled": True},
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            json_provider = JsonFileProvider(filepath)
            initialize_feature_flags(json_provider)

            flags = get_feature_flags()
            assert not flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)
            assert flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)

            # Switch to environment provider
            manager_module._global_manager = None
            os.environ["FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING"] = "true"
            os.environ["FEATURE_FLAG_ENABLE_SEGMENT_CACHING"] = "false"

            env_provider = EnvironmentVariableProvider()
            initialize_feature_flags(env_provider)

            flags = get_feature_flags()
            assert flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)
            assert not flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)

        finally:
            Path(filepath).unlink()
            os.environ.pop("FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING", None)
            os.environ.pop("FEATURE_FLAG_ENABLE_SEGMENT_CACHING", None)
            manager_module._global_manager = None

    @pytest.mark.integration
    def test_real_world_flag_evaluation_flow(self):
        """Test realistic flag evaluation with multiple flag types."""
        import idea_shared.feature_flags.manager as manager_module

        manager_module._global_manager = None

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {
                "flags": {
                    "enable_experimental_validation": {"enabled": True},
                    "enable_parallel_processing": {"enabled": True},
                    "enable_segment_caching": {"enabled": False},
                    "fcd_update_interval_override": {"value": 10},
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            initialize_feature_flags(provider)

            flags = get_feature_flags()

            # Test boolean flags
            assert flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION)
            assert flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)
            assert not flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)

            # Test integer flag with override
            interval = flags.get_int(
                FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=5
            )
            assert interval == 10

            # Test flag without override uses default
            disturbance_interval = flags.get_int(
                FeatureFlag.DISTURBANCE_UPDATE_INTERVAL_OVERRIDE, default=60
            )
            assert disturbance_interval == 60

        finally:
            Path(filepath).unlink()
            manager_module._global_manager = None

    @pytest.mark.integration
    def test_provider_handles_missing_flags_gracefully(self):
        """Test that providers handle missing flags with defaults."""
        import idea_shared.feature_flags.manager as manager_module

        manager_module._global_manager = None

        # Create JSON file with only some flags
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {
                "flags": {
                    "enable_parallel_processing": {"enabled": False},
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            initialize_feature_flags(provider)

            flags = get_feature_flags()

            # Configured flag should use configured value
            assert not flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)

            # Missing flags should use defaults from FlagDefaults
            assert not flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION)
            assert not flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)

        finally:
            Path(filepath).unlink()
            manager_module._global_manager = None

    @pytest.mark.integration
    def test_environment_provider_with_mixed_flags(self):
        """Test environment provider with boolean, int, and missing flags."""
        import idea_shared.feature_flags.manager as manager_module

        manager_module._global_manager = None

        # Set some environment variables
        os.environ["FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING"] = "true"
        os.environ["FEATURE_FLAG_FCD_UPDATE_INTERVAL_OVERRIDE"] = "15"

        try:
            provider = EnvironmentVariableProvider()
            initialize_feature_flags(provider)

            flags = get_feature_flags()

            # Test boolean flag from environment
            assert flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)

            # Test integer flag from environment
            interval = flags.get_int(
                FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=5
            )
            assert interval == 15

            # Test missing flag uses default
            assert not flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)

        finally:
            os.environ.pop("FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING", None)
            os.environ.pop("FEATURE_FLAG_FCD_UPDATE_INTERVAL_OVERRIDE", None)
            manager_module._global_manager = None

    @pytest.mark.integration
    def test_flag_evaluation_with_invalid_json(self):
        """Test that invalid JSON falls back to defaults gracefully."""
        import idea_shared.feature_flags.manager as manager_module

        manager_module._global_manager = None

        # Create invalid JSON file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("invalid json content {]")
            filepath = f.name

        try:
            provider = JsonFileProvider(filepath)
            initialize_feature_flags(provider)

            flags = get_feature_flags()

            # All flags should use defaults
            assert flags.is_enabled(
                FeatureFlag.ENABLE_PARALLEL_PROCESSING
            )  # default True
            assert not flags.is_enabled(
                FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION
            )  # default False

        finally:
            Path(filepath).unlink()
            manager_module._global_manager = None


class TestCrossProviderConsistency:
    """Test that providers behave consistently with same config."""

    @pytest.mark.integration
    def test_json_and_env_providers_return_same_values(self):
        """Test that JSON and env providers return same values for same config."""
        import idea_shared.feature_flags.manager as manager_module

        # Test data
        test_flags = {
            "enable_parallel_processing": True,
            "enable_segment_caching": False,
            "fcd_update_interval_override": 20,
        }

        # Test with JSON provider
        manager_module._global_manager = None
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            data = {
                "flags": {
                    "enable_parallel_processing": {"enabled": True},
                    "enable_segment_caching": {"enabled": False},
                    "fcd_update_interval_override": {"value": 20},
                }
            }
            json.dump(data, f)
            filepath = f.name

        try:
            json_provider = JsonFileProvider(filepath)
            initialize_feature_flags(json_provider)
            json_flags = get_feature_flags()

            json_parallel = json_flags.is_enabled(
                FeatureFlag.ENABLE_PARALLEL_PROCESSING
            )
            json_caching = json_flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)
            json_interval = json_flags.get_int(
                FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=5
            )

            # Test with environment provider
            manager_module._global_manager = None
            os.environ["FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING"] = "true"
            os.environ["FEATURE_FLAG_ENABLE_SEGMENT_CACHING"] = "false"
            os.environ["FEATURE_FLAG_FCD_UPDATE_INTERVAL_OVERRIDE"] = "20"

            env_provider = EnvironmentVariableProvider()
            initialize_feature_flags(env_provider)
            env_flags = get_feature_flags()

            env_parallel = env_flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING)
            env_caching = env_flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)
            env_interval = env_flags.get_int(
                FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=5
            )

            # Both providers should return same values
            assert json_parallel == env_parallel == True
            assert json_caching == env_caching == False
            assert json_interval == env_interval == 20

        finally:
            Path(filepath).unlink()
            os.environ.pop("FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING", None)
            os.environ.pop("FEATURE_FLAG_ENABLE_SEGMENT_CACHING", None)
            os.environ.pop("FEATURE_FLAG_FCD_UPDATE_INTERVAL_OVERRIDE", None)
            manager_module._global_manager = None

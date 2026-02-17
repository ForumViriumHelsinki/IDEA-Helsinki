"""Unit tests for feature flag constants and defaults."""

import pytest

from idea_shared.feature_flags.flags import FeatureFlag, FlagDefaults


class TestFeatureFlag:
    """Tests for FeatureFlag enum."""

    @pytest.mark.unit
    def test_flag_names_are_strings(self):
        """All flag enum values are strings."""
        for flag in FeatureFlag:
            assert isinstance(flag.value, str)
            assert len(flag.value) > 0

    @pytest.mark.unit
    def test_flag_names_use_snake_case(self):
        """Flag names use snake_case convention."""
        for flag in FeatureFlag:
            assert flag.value.islower()
            assert " " not in flag.value

    @pytest.mark.unit
    def test_specific_flags_exist(self):
        """Verify expected flags are defined."""
        expected_flags = [
            "enable_experimental_validation",
            "enable_parallel_processing",
            "enable_segment_caching",
            "enable_enhanced_logging",
        ]
        flag_values = [f.value for f in FeatureFlag]
        for expected in expected_flags:
            assert expected in flag_values


class TestFlagDefaults:
    """Tests for FlagDefaults class."""

    @pytest.mark.unit
    def test_boolean_defaults_are_bool(self):
        """Boolean flag defaults are bool type."""
        boolean_flags = [
            FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION,
            FeatureFlag.ENABLE_PARALLEL_PROCESSING,
            FeatureFlag.ENABLE_SEGMENT_CACHING,
            FeatureFlag.ENABLE_ENHANCED_LOGGING,
        ]
        for flag in boolean_flags:
            default = FlagDefaults.get_default(flag)
            assert isinstance(default, bool)

    @pytest.mark.unit
    def test_get_default_for_known_flag(self):
        """get_default returns correct value for known flags."""
        default = FlagDefaults.get_default(FeatureFlag.ENABLE_PARALLEL_PROCESSING)
        assert default is True

        default = FlagDefaults.get_default(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION)
        assert default is False

    @pytest.mark.unit
    def test_get_default_for_numeric_flag(self):
        """get_default handles numeric flags correctly."""
        default = FlagDefaults.get_default(FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE)
        assert default is None

    @pytest.mark.unit
    def test_all_flags_have_defaults(self):
        """Every flag enum has a corresponding default."""
        for flag in FeatureFlag:
            # Should not raise AttributeError
            default = FlagDefaults.get_default(flag)
            # Default can be any type including None
            assert default is not None or default is None

    @pytest.mark.unit
    def test_get_default_converts_snake_case_to_upper(self):
        """get_default correctly converts snake_case to UPPER_SNAKE_CASE."""
        # Test with different flag types to ensure conversion works
        test_cases = [
            (FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION, False),
            (FeatureFlag.ENABLE_PARALLEL_PROCESSING, True),
            (FeatureFlag.ENABLE_SEGMENT_CACHING, False),
            (FeatureFlag.ENABLE_ENHANCED_LOGGING, False),
            (FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, None),
        ]

        for flag, expected_value in test_cases:
            actual = FlagDefaults.get_default(flag)
            assert actual == expected_value, (
                f"Expected {flag.value} to have default {expected_value}, got {actual}"
            )

    @pytest.mark.unit
    def test_get_default_raises_for_unknown_flag(self):
        """get_default raises AttributeError for undefined flags."""

        # Create a flag enum value that doesn't have a corresponding default
        class FakeFlag(str):
            value = "nonexistent_flag"

        fake_flag = FakeFlag()

        with pytest.raises(AttributeError):
            FlagDefaults.get_default(fake_flag)

"""Tests for IDEAError handling in profile generation."""

import numpy as np
import pandas as pd
import pytest

from idea_shared.lib.idea.exceptions import IDEAError
from idea_shared.lib.idea.profile.util import does_profile_has_enough_data


class TestDoesProfileHasEnoughData:
    """Tests for does_profile_has_enough_data function."""

    def test_raises_idea_error_when_insufficient_quality_buckets(self):
        """Test raises IDEAError when quality threshold not met."""
        # Create profile with most values above MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 (12)
        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * 24,
            "hour_of_day": list(range(24)),
            "fcd_mean_median": [10.0] * 24,
            # All values above threshold of 12
            "max_consecutive_zeros_q95": [15.0] * 24,
            "max_consecutive_zeros_or_ones_q95": [20.0] * 24,
            "number_of_hours": [50] * 24,
        })

        with pytest.raises(IDEAError) as exc_info:
            does_profile_has_enough_data(profile)

        assert "Not enough fcd input data" in str(exc_info.value.message)
        assert "hour-of-week buckets pass quality checks" in str(exc_info.value.message)

    def test_passes_when_sufficient_quality_buckets(self):
        """Test passes when enough buckets pass quality threshold."""
        # Create profile with values below MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 (12)
        # Need at least THRESHOLD_OF_USEFUL_DATA_PROFILE (30) buckets passing
        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * 168,  # Full week
            "hour_of_day": list(range(24)) * 7,
            "fcd_mean_median": [10.0] * 168,
            # All values below threshold of 12
            "max_consecutive_zeros_q95": [5.0] * 168,
            "max_consecutive_zeros_or_ones_q95": [8.0] * 168,
            "number_of_hours": [50] * 168,
        })

        # Should not raise
        does_profile_has_enough_data(profile)

    def test_error_message_includes_diagnostic_info(self):
        """Test error message includes diagnostic counts."""
        # MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 is 35, so values >= 35 fail
        # Create profile with exactly 10 passing buckets (below threshold of 30)
        passing_values = [5.0] * 10  # Below threshold of 35 (pass)
        failing_values = [40.0] * 14  # Above threshold of 35 (fail)
        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * 24,
            "hour_of_day": list(range(24)),
            "fcd_mean_median": [10.0] * 24,
            "max_consecutive_zeros_q95": passing_values + failing_values,
            "max_consecutive_zeros_or_ones_q95": [8.0] * 24,
            "number_of_hours": [50] * 24,
        })

        with pytest.raises(IDEAError) as exc_info:
            does_profile_has_enough_data(profile)

        error_msg = str(exc_info.value.message)
        # Should include the actual count
        assert "10" in error_msg
        assert "24" in error_msg  # Total buckets

    def test_boundary_condition_exactly_at_threshold(self):
        """Test behavior at exactly the threshold boundary."""
        from idea_shared.lib.idea.constants import (
            MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95,
            THRESHOLD_OF_USEFUL_DATA_PROFILE,
        )

        # Create profile with exactly THRESHOLD_OF_USEFUL_DATA_PROFILE passing buckets
        num_passing = THRESHOLD_OF_USEFUL_DATA_PROFILE
        total_buckets = num_passing + 10

        # Values just below the max acceptable (passing)
        passing_values = [MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 - 1] * num_passing
        # Values just above the max acceptable (failing)
        failing_values = [MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 + 1] * 10

        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * total_buckets,
            "hour_of_day": list(range(total_buckets)),
            "fcd_mean_median": [10.0] * total_buckets,
            "max_consecutive_zeros_q95": passing_values + failing_values,
            "max_consecutive_zeros_or_ones_q95": [8.0] * total_buckets,
            "number_of_hours": [50] * total_buckets,
        })

        # Exactly at threshold should pass (>= not >)
        does_profile_has_enough_data(profile)

    def test_boundary_condition_one_below_threshold(self):
        """Test fails when one bucket below threshold."""
        from idea_shared.lib.idea.constants import (
            MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95,
            THRESHOLD_OF_USEFUL_DATA_PROFILE,
        )

        # One below the threshold
        num_passing = THRESHOLD_OF_USEFUL_DATA_PROFILE - 1
        num_failing = 11

        passing_values = [MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 - 1] * num_passing
        failing_values = [MAX_ACCEPTABLE_CONSECUTIVE_ZEROS_Q95 + 1] * num_failing

        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * (num_passing + num_failing),
            "hour_of_day": list(range(num_passing + num_failing)),
            "fcd_mean_median": [10.0] * (num_passing + num_failing),
            "max_consecutive_zeros_q95": passing_values + failing_values,
            "max_consecutive_zeros_or_ones_q95": [8.0] * (num_passing + num_failing),
            "number_of_hours": [50] * (num_passing + num_failing),
        })

        with pytest.raises(IDEAError):
            does_profile_has_enough_data(profile)

    def test_handles_nan_values(self):
        """Test handles NaN values in the profile data."""
        # Profile with some NaN values - they won't count as passing
        profile = pd.DataFrame({
            "day_of_week": ["Monday"] * 24,
            "hour_of_day": list(range(24)),
            "fcd_mean_median": [10.0] * 24,
            "max_consecutive_zeros_q95": [np.nan] * 24,  # All NaN
            "max_consecutive_zeros_or_ones_q95": [8.0] * 24,
            "number_of_hours": [50] * 24,
        })

        # NaN < threshold is False, so none pass
        with pytest.raises(IDEAError):
            does_profile_has_enough_data(profile)

    def test_empty_profile_raises_error(self):
        """Test empty profile raises IDEAError."""
        profile = pd.DataFrame({
            "day_of_week": [],
            "hour_of_day": [],
            "fcd_mean_median": [],
            "max_consecutive_zeros_q95": [],
            "max_consecutive_zeros_or_ones_q95": [],
            "number_of_hours": [],
        })

        with pytest.raises(IDEAError):
            does_profile_has_enough_data(profile)

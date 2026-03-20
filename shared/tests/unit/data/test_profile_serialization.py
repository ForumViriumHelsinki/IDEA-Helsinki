"""Tests for profile serialization utilities."""

import numpy as np
import pandas as pd
import pytest

from idea_shared.data.profile_serialization import (
    deserialize_profile,
    serialize_profile,
)


class TestProfileSerialization:
    """Tests for Parquet round-trip serialization."""

    @pytest.mark.unit
    def test_round_trip_fidelity(self):
        """Serialize and deserialize a DataFrame, verify exact equality."""
        df = pd.DataFrame(
            {
                "hour": list(range(168)),
                "mean_speed": np.random.default_rng(42).uniform(20, 80, 168),
                "std_speed": np.random.default_rng(42).uniform(1, 10, 168),
                "count": np.random.default_rng(42).integers(10, 200, 168),
                "confidence": np.random.default_rng(42).uniform(0.5, 1.0, 168),
                "day_of_week": [i // 24 for i in range(168)],
            }
        )
        data = serialize_profile(df)
        result = deserialize_profile(data)

        assert list(result.columns) == list(df.columns)
        assert len(result) == len(df)
        pd.testing.assert_frame_equal(result, df)

    @pytest.mark.unit
    def test_empty_dataframe(self):
        """Round-trip an empty DataFrame."""
        df = pd.DataFrame({"a": [], "b": []})
        data = serialize_profile(df)
        result = deserialize_profile(data)
        assert len(result) == 0
        assert list(result.columns) == ["a", "b"]

    @pytest.mark.unit
    def test_preserves_dtypes(self):
        """Verify that numeric dtypes are preserved through serialization."""
        df = pd.DataFrame(
            {
                "int_col": pd.array([1, 2, 3], dtype="int64"),
                "float_col": pd.array([1.1, 2.2, 3.3], dtype="float64"),
                "str_col": ["a", "b", "c"],
            }
        )
        data = serialize_profile(df)
        result = deserialize_profile(data)
        assert result["int_col"].dtype == np.int64
        assert result["float_col"].dtype == np.float64

    @pytest.mark.unit
    def test_output_is_bytes(self):
        """Serialized output should be raw bytes."""
        df = pd.DataFrame({"x": [1]})
        data = serialize_profile(df)
        assert isinstance(data, bytes)
        assert len(data) > 0

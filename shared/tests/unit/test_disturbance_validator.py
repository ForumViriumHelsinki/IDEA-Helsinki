"""Unit tests for DisturbanceValidator module."""

from datetime import UTC, datetime, timedelta

import pytest

from idea_shared.lib import DisturbanceValidator


class TestValidateDisturbanceDates:
    """Tests for validate_disturbance_dates function."""

    @pytest.mark.unit
    def test_empty_features_returns_none(self):
        """Empty features list returns None."""
        disturbance_data = {"features": []}
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None

    @pytest.mark.unit
    def test_missing_features_key_returns_none(self):
        """Missing features key returns None."""
        disturbance_data = {"other_key": "value"}
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None

    @pytest.mark.unit
    def test_features_not_list_returns_none(self):
        """Non-list features returns None."""
        disturbance_data = {"features": "not a list"}
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None

    @pytest.mark.unit
    def test_valid_current_disturbance(self, freeze_time):
        """Test validation of currently active disturbance."""
        with freeze_time("2024-02-15"):
            validation_date = datetime(2024, 1, 1, tzinfo=UTC)
            disturbance_data = {
                "features": [
                    {
                        "properties": {
                            "tyo_alkaa": "2024-02-10",
                            "tyo_paattyy": "2025-12-31",
                            "name": "Test disturbance",
                        },
                        "geometry": {"type": "Polygon"},
                    }
                ],
                "type": "FeatureCollection",
            }

            result = DisturbanceValidator.validate_disturbance_dates(
                validation_date, disturbance_data
            )

            assert result is not None
            assert len(result["features"]) == 1
            assert result["totalFeatures"] == 1
            assert result["numberMatched"] == 1

    @pytest.mark.unit
    def test_valid_future_disturbance(self, freeze_time):
        """Test validation of future disturbance."""
        with freeze_time("2024-02-15"):
            validation_date = datetime(2024, 1, 1, tzinfo=UTC)
            future_date = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
            disturbance_data = {
                "features": [
                    {
                        "properties": {
                            "tyo_alkaa": future_date,
                            "tyo_paattyy": "2025-12-31",
                            "name": "Future disturbance",
                        },
                        "geometry": {"type": "Polygon"},
                    }
                ]
            }

            result = DisturbanceValidator.validate_disturbance_dates(
                validation_date, disturbance_data
            )

            assert result is not None
            assert len(result["features"]) == 1

    @pytest.mark.unit
    def test_invalid_old_disturbance(self, freeze_time):
        """Disturbances before validation date are filtered out."""
        with freeze_time("2024-02-15"):
            validation_date = datetime(2024, 2, 1, tzinfo=UTC)
            disturbance_data = {
                "features": [
                    {
                        "properties": {
                            "tyo_alkaa": "2024-01-15",  # Before validation date
                            "tyo_paattyy": "2025-12-31",
                            "name": "Old disturbance",
                        }
                    }
                ]
            }

            result = DisturbanceValidator.validate_disturbance_dates(
                validation_date, disturbance_data
            )

            assert result is None  # All disturbances filtered out

    @pytest.mark.unit
    def test_mixed_valid_invalid_disturbances(self, freeze_time):
        """Test filtering mixed valid and invalid disturbances."""
        with freeze_time("2024-02-15"):
            validation_date = datetime(2024, 1, 1, tzinfo=UTC)
            disturbance_data = {
                "features": [
                    {
                        "properties": {
                            "tyo_alkaa": "2023-12-15",  # Too old
                            "tyo_paattyy": "2025-12-31",
                            "name": "Old",
                        }
                    },
                    {
                        "properties": {
                            "tyo_alkaa": "2024-02-10",  # Valid
                            "tyo_paattyy": "2025-12-31",
                            "name": "Current",
                        }
                    },
                    {
                        "properties": {
                            "tyo_alkaa": "2024-03-01",  # Future, valid
                            "tyo_paattyy": "2025-12-31",
                            "name": "Future",
                        }
                    },
                ]
            }

            result = DisturbanceValidator.validate_disturbance_dates(
                validation_date, disturbance_data
            )

            assert result is not None
            assert len(result["features"]) == 2
            assert result["features"][0]["properties"]["name"] == "Current"
            assert result["features"][1]["properties"]["name"] == "Future"

    @pytest.mark.unit
    def test_malformed_date_skipped(self):
        """Disturbances with malformed dates are skipped."""
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)
        disturbance_data = {
            "features": [
                {
                    "properties": {
                        "tyo_alkaa": "invalid-date",
                        "name": "Bad date",
                    }
                }
            ]
        }

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None  # Malformed entry filtered out

    @pytest.mark.unit
    def test_missing_date_field_skipped(self):
        """Disturbances without date field are skipped."""
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)
        disturbance_data = {
            "features": [{"properties": {"name": "No date"}}]  # Missing tyo_alkaa
        }

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None

    @pytest.mark.unit
    def test_non_dict_feature_skipped(self):
        """Non-dictionary features are skipped."""
        validation_date = datetime(2024, 1, 1, tzinfo=UTC)
        disturbance_data = {"features": ["not a dict", 123, None]}

        result = DisturbanceValidator.validate_disturbance_dates(
            validation_date, disturbance_data
        )

        assert result is None

    @pytest.mark.unit
    def test_metadata_fields_updated(self, freeze_time):
        """Metadata fields are correctly updated."""
        with freeze_time("2024-02-15T12:00:00Z"):
            validation_date = datetime(2024, 1, 1, tzinfo=UTC)
            disturbance_data = {
                "features": [
                    {
                        "properties": {"tyo_alkaa": "2024-02-10", "tyo_paattyy": "2025-12-31"},
                        "type": "Feature",
                    }
                ],
                "type": "FeatureCollection",
                "totalFeatures": 100,  # Will be updated
                "numberMatched": 100,  # Will be updated
                "numberReturned": 100,  # Will be updated
            }

            result = DisturbanceValidator.validate_disturbance_dates(
                validation_date, disturbance_data
            )

            assert result is not None
            assert result["totalFeatures"] == 1
            assert result["numberMatched"] == 1
            assert result["numberReturned"] == 1
            assert "timeStamp" in result
            assert result["timeStamp"] == "2024-02-15T12:00:00Z"
            assert result["type"] == "FeatureCollection"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Unit tests for TomTomFcdAggregator module.

Tests the core FCD data aggregation logic including confidence conversion,
data validation, transformation, sorting, and updating operations.

Following TDD principles: Tests use real data structures with minimal mocking.
"""

import pytest

from idea_shared.lib import TomTomFcdAggregator


class TestConfidenceConversion:
    """Tests for convert_confidence_to_fcd_num function."""

    def test_none_confidence_returns_none(self):
        """None confidence should return None for IDEA algorithm."""
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(None)  # type: ignore[arg-type]
        assert result is None

    def test_zero_confidence_returns_zero(self):
        """Confidence of 0 should map to FCD value 0."""
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(0)
        assert result == 0

    def test_low_confidence_returns_zero(self):
        """Confidence <= 70 should map to FCD value 0."""
        assert TomTomFcdAggregator.convert_confidence_to_fcd_num(50) == 0
        assert TomTomFcdAggregator.convert_confidence_to_fcd_num(70) == 0

    def test_max_confidence_returns_ten(self):
        """Confidence of 100 should map to FCD value 10."""
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(100)
        assert result == 10

    def test_mid_range_confidence_scales_linearly(self):
        """Confidence between 70-100 should scale linearly to 0-10."""
        # 85 is halfway between 70 and 100, should map to 5
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(85)
        assert result == 5

        # 77 should map to approximately 2
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(77)
        assert result == 2

        # 94 should map to approximately 8
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(94)
        assert result == 8

    def test_boundary_values(self):
        """Test boundary values of confidence range."""
        # Just above threshold
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(71)
        assert result == 0

        # Just below max
        result = TomTomFcdAggregator.convert_confidence_to_fcd_num(99)
        assert result == 10


class TestValidation:
    """Tests for validate_tomtom_aggregation_file function."""

    def test_valid_file_passes_validation(self):
        """Valid aggregation file should pass validation unchanged."""
        valid_data = {
            "segmentId": {
                "12345": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[24.9384, 60.1699], [24.9394, 60.1709]],
                    },
                    "detailedSegment": {
                        "date": {
                            "2025-01-01T12:00:00": {"properties": {"currentSpeed": 50}}
                        }
                    },
                }
            }
        }
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(valid_data)
        assert result == valid_data

    def test_missing_segment_id_returns_empty(self):
        """Missing segmentId key should return empty dict."""
        invalid_data = {"notSegmentId": {}}
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_non_dict_segment_id_returns_empty(self):
        """SegmentId not being a dict should return empty dict."""
        invalid_data = {"segmentId": "not_a_dict"}
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_non_numeric_segment_key_returns_empty(self):
        """Non-numeric segment ID keys should return empty dict."""
        invalid_data = {
            "segmentId": {
                "abc": {  # Not a digit string
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {"date": {}},
                }
            }
        }
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_missing_geometry_returns_empty(self):
        """Missing geometry key should return empty dict."""
        invalid_data = {"segmentId": {"12345": {"detailedSegment": {"date": {}}}}}
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_missing_detailed_segment_returns_empty(self):
        """Missing detailedSegment key should return empty dict."""
        invalid_data = {
            "segmentId": {
                "12345": {"geometry": {"type": "LineString", "coordinates": []}}
            }
        }
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_invalid_geometry_type_returns_empty(self):
        """Geometry type other than LineString should return empty dict."""
        invalid_data = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "Polygon", "coordinates": []},
                    "detailedSegment": {"date": {}},
                }
            }
        }
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}

    def test_malformed_coordinates_returns_empty(self):
        """Malformed coordinates should return empty dict."""
        # Coordinates not a list of [lon, lat] pairs
        invalid_data = {
            "segmentId": {
                "12345": {
                    "geometry": {
                        "type": "LineString",
                        "coordinates": ["not", "coords"],  # Invalid
                    },
                    "detailedSegment": {"date": {}},
                }
            }
        }
        result = TomTomFcdAggregator.validate_tomtom_aggregation_file(invalid_data)
        assert result == {}


class TestTransformation:
    """Tests for transform_single_tomtom_json_data_for_aggregation function."""

    def test_transform_single_segment(self):
        """Transform single TomTom segment into aggregation format."""
        raw_data = {
            "detailedSegments": [
                {
                    "segmentIdStr": "12345",
                    "currentSpeed": 50,
                    "averageSpeed": 52,
                    "typicalSpeed": 55,
                    "confidence": 85,
                    "shape": [
                        {"longitude": 24.9384, "latitude": 60.1699},
                        {"longitude": 24.9394, "latitude": 60.1709},
                    ],
                }
            ]
        }

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        assert "segmentId" in result
        assert "12345" in result["segmentId"]
        segment = result["segmentId"]["12345"]

        # Check geometry
        assert segment["geometry"]["type"] == "LineString"
        assert len(segment["geometry"]["coordinates"]) == 2
        assert segment["geometry"]["coordinates"][0] == [24.9384, 60.1699]

        # Check detailed segment
        assert "detailedSegment" in segment
        assert "date" in segment["detailedSegment"]
        assert "2025-01-01T12:00:00" in segment["detailedSegment"]["date"]

        # Check properties
        props = segment["detailedSegment"]["date"]["2025-01-01T12:00:00"]["properties"]
        assert props["currentSpeed"] == 50
        assert props["averageSpeed"] == 52
        assert props["typicalSpeed"] == 55
        assert props["confidence_level"] == 85
        assert props["fcd_coverage"] == 5  # 85 confidence maps to 5

    def test_transform_multiple_segments(self):
        """Transform multiple TomTom segments."""
        raw_data = {
            "detailedSegments": [
                {
                    "segmentIdStr": "111",
                    "currentSpeed": 40,
                    "confidence": 90,
                    "shape": [{"longitude": 24.9, "latitude": 60.1}],
                },
                {
                    "segmentIdStr": "222",
                    "currentSpeed": 60,
                    "confidence": 95,
                    "shape": [{"longitude": 24.95, "latitude": 60.15}],
                },
            ]
        }

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        assert len(result["segmentId"]) == 2
        assert "111" in result["segmentId"]
        assert "222" in result["segmentId"]

    def test_transform_handles_numeric_segment_id(self):
        """Transform should handle numeric segmentId (not segmentIdStr)."""
        raw_data = {
            "detailedSegments": [
                {
                    "segmentId": 99999,  # Numeric instead of string
                    "currentSpeed": 50,
                    "confidence": 80,
                    "shape": [{"longitude": 24.9, "latitude": 60.1}],
                }
            ]
        }

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        assert "99999" in result["segmentId"]

    def test_transform_skips_segment_without_id(self):
        """Transform should skip segments without ID."""
        raw_data = {
            "detailedSegments": [
                {
                    "currentSpeed": 50,
                    "confidence": 80,
                    "shape": [],
                    # Missing both segmentId and segmentIdStr
                }
            ]
        }

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        assert result["segmentId"] == {}

    def test_transform_handles_missing_shape_data(self):
        """Transform should handle missing or invalid shape data."""
        raw_data = {
            "detailedSegments": [
                {
                    "segmentIdStr": "12345",
                    "currentSpeed": 50,
                    "confidence": 80,
                    # Missing shape
                }
            ]
        }

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        # Should still create segment with empty coordinates
        assert "12345" in result["segmentId"]
        assert result["segmentId"]["12345"]["geometry"]["coordinates"] == []

    def test_transform_invalid_detailed_segments(self):
        """Transform should return empty dict for invalid detailedSegments."""
        raw_data = {"detailedSegments": "not_a_list"}

        result = TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
            raw_data, "2025-01-01T12:00:00", "test_blob.json"
        )

        assert result == {}


class TestSorting:
    """Tests for sort_tomtom_data_aggregation_file_by_date function."""

    def test_sort_dates_chronologically(self):
        """Dates should be sorted in chronological order."""
        data = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {
                            "2025-01-03T12:00:00": {"properties": {}},
                            "2025-01-01T12:00:00": {"properties": {}},
                            "2025-01-02T12:00:00": {"properties": {}},
                        }
                    },
                }
            }
        }

        result = TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(data)

        dates = list(result["segmentId"]["12345"]["detailedSegment"]["date"].keys())
        assert dates == [
            "2025-01-01T12:00:00",
            "2025-01-02T12:00:00",
            "2025-01-03T12:00:00",
        ]

    def test_sort_handles_empty_data(self):
        """Sort should handle empty segmentId dict."""
        data = {"segmentId": {}}
        result = TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(data)
        assert result == data

    def test_sort_handles_malformed_dates(self):
        """Sort should handle malformed date strings gracefully."""
        data = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {
                            "invalid-date": {"properties": {}},
                            "2025-01-01T12:00:00": {"properties": {}},
                        }
                    },
                }
            }
        }

        # Should not crash, just log warning
        result = TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(data)
        assert "12345" in result["segmentId"]


class TestUpdate:
    """Tests for update_tomtom_json_data_for_aggregation_file function."""

    def test_update_empty_base_file(self):
        """Updating empty base file should return new file."""
        new_file = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T12:00:00": {"properties": {"speed": 50}}}
                    },
                }
            }
        }

        result = TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
            new_file, {}
        )

        assert result == new_file

    def test_update_adds_new_segment(self):
        """Update should add new segment to existing file."""
        existing_file = {
            "segmentId": {
                "111": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T12:00:00": {"properties": {}}}
                    },
                }
            }
        }

        new_file = {
            "segmentId": {
                "222": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T13:00:00": {"properties": {}}}
                    },
                }
            }
        }

        result = TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
            new_file, existing_file
        )

        assert "111" in result["segmentId"]
        assert "222" in result["segmentId"]

    def test_update_adds_new_timestamp_to_existing_segment(self):
        """Update should add new timestamp to existing segment."""
        existing_file = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T12:00:00": {"properties": {"speed": 50}}}
                    },
                }
            }
        }

        new_file = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T13:00:00": {"properties": {"speed": 55}}}
                    },
                }
            }
        }

        result = TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
            new_file, existing_file
        )

        dates = result["segmentId"]["12345"]["detailedSegment"]["date"]
        assert "2025-01-01T12:00:00" in dates
        assert "2025-01-01T13:00:00" in dates

    def test_update_skips_duplicate_timestamps(self):
        """Update should not overwrite existing timestamps."""
        existing_file = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T12:00:00": {"properties": {"speed": 50}}}
                    },
                }
            }
        }

        new_file = {
            "segmentId": {
                "12345": {
                    "geometry": {"type": "LineString", "coordinates": []},
                    "detailedSegment": {
                        "date": {"2025-01-01T12:00:00": {"properties": {"speed": 999}}}
                    },
                }
            }
        }

        result = TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
            new_file, existing_file
        )

        # Should keep original value (50), not overwrite with 999
        speed = result["segmentId"]["12345"]["detailedSegment"]["date"][
            "2025-01-01T12:00:00"
        ]["properties"]["speed"]
        assert speed == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

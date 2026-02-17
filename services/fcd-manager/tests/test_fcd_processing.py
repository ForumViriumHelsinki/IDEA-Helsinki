"""
Tests for streaming FCD blob processing.

This module tests the batch-based streaming approach that processes Azure blobs
in batches instead of loading everything into memory at once.

These tests verify REAL FCD data transformation logic by:
1. Only mocking Azure blob download (external dependency)
2. Using realistic TomTom JSON test data
3. Asserting on actual transformed output structure and values

This ensures tests fail when real bugs are introduced in the processing pipeline.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fcd_processing import process_date_range_streaming


# Test fixture: Realistic TomTom JSON data
def create_tomtom_json_blob(segment_id: str, speed: int, confidence: int) -> bytes:
    """
    Create realistic TomTom JSON blob content for testing.

    This matches the actual TomTom API response format.
    """
    tomtom_data = {
        "detailedSegments": [
            {
                "segmentIdStr": segment_id,
                "currentSpeed": speed,
                "averageSpeed": speed + 5,
                "typicalSpeed": speed + 10,
                "confidence": confidence,
                "shape": [
                    {"longitude": 24.9384, "latitude": 60.1699},
                    {"longitude": 24.9394, "latitude": 60.1709},
                ],
            }
        ]
    }
    return json.dumps(tomtom_data).encode("utf-8")


class TestStreamingBlobProcessing:
    """Tests for streaming blob processing functionality with REAL data transformation."""

    def test_process_empty_blob_list(self):
        """Test that empty blob list returns empty generator."""
        azure_manager = MagicMock()
        azure_manager.get_blobs_in_range.return_value = []

        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        assert len(results) == 0

    def test_process_single_batch(self):
        """
        Test processing a single batch with REAL FCD transformation logic.

        This test verifies the entire data pipeline:
        1. Blob timestamp extraction from filename
        2. JSON parsing from bytes
        3. TomTom data transformation to FCD model
        4. Aggregation and sorting

        Only Azure blob download is mocked (external dependency).
        """
        azure_manager = MagicMock()

        # Setup: Mock blob with realistic name (must match timestamp pattern)
        mock_blob = MagicMock()
        mock_blob.name = "fcd_data_2025-01-01T12:00:00.json"
        azure_manager.get_blobs_in_range.return_value = [mock_blob]

        # Setup: Realistic TomTom JSON content
        blob_content = create_tomtom_json_blob(
            segment_id="12345", speed=50, confidence=85
        )
        azure_manager.download_blob_content.return_value = blob_content

        # Execute: NO MOCKING - Let real FCD processing run
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Verify actual transformed output
        assert len(results) == 1, "Should yield exactly one batch"

        batch_data = results[0]
        assert "segmentId" in batch_data, "Output should follow FCD data model"
        assert "12345" in batch_data["segmentId"], "Segment ID should be preserved"

        segment_data = batch_data["segmentId"]["12345"]

        # Verify geometry was transformed correctly
        assert "geometry" in segment_data
        assert segment_data["geometry"]["type"] == "LineString"
        assert len(segment_data["geometry"]["coordinates"]) == 2
        assert segment_data["geometry"]["coordinates"][0] == [24.9384, 60.1699]

        # Verify detailed segment with date and properties
        assert "detailedSegment" in segment_data
        assert "date" in segment_data["detailedSegment"]

        # There should be exactly one timestamp
        dates = segment_data["detailedSegment"]["date"]
        assert len(dates) == 1
        assert "2025-01-01T12:00:00" in dates

        # Verify properties were transformed correctly
        properties = dates["2025-01-01T12:00:00"]["properties"]
        assert properties["currentSpeed"] == 50
        assert properties["averageSpeed"] == 55  # speed + 5
        assert properties["typicalSpeed"] == 60  # speed + 10
        assert properties["confidence_level"] == 85
        # confidence 85 -> fcd_coverage calculation: ((85-70)/(100-70))*10 = 5
        assert properties["fcd_coverage"] == 5

    def test_process_multiple_batches(self):
        """
        Test processing multiple batches with REAL batching logic.

        Verifies that:
        1. Blobs are correctly divided into batches
        2. Each batch is processed independently
        3. Batch size parameter is respected
        """
        azure_manager = MagicMock()

        # Create 100 mock blobs (will be processed in 2 batches of 50)
        mock_blobs = []
        for i in range(100):
            mock_blob = MagicMock()
            # Create realistic filenames with incrementing timestamps
            # Format: YYYY-MM-DDTHH:MM:SS (required by extract_timestamp_str_from_file_name)
            hour = i // 60
            minute = i % 60
            mock_blob.name = f"fcd_data_2025-01-01T{hour:02d}:{minute:02d}:00.json"
            mock_blobs.append(mock_blob)

        azure_manager.get_blobs_in_range.return_value = mock_blobs

        # Each blob returns realistic TomTom data
        # Use different segment IDs to verify batch independence
        def mock_download(blob_name):
            # Extract timestamp from filename to create different segment IDs
            import re

            # Format: fcd_data_2025-01-01THH:MM:SS.json
            match = re.search(r"T(\d{2}):(\d{2}):\d{2}", blob_name)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                idx = hour * 60 + minute  # Convert to minutes since midnight
                return create_tomtom_json_blob(
                    segment_id=f"seg{idx}", speed=50 + (idx % 10), confidence=80
                )
            return create_tomtom_json_blob(
                segment_id="default", speed=50, confidence=80
            )

        azure_manager.download_blob_content.side_effect = mock_download

        # Execute: NO MOCKING - Let real batch processing run
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Should yield 2 batches (100 blobs / 50 batch_size = 2)
        assert len(results) == 2, "Should process 100 blobs in 2 batches of 50"

        # Verify each batch contains valid FCD data
        for i, batch in enumerate(results):
            assert "segmentId" in batch, f"Batch {i} should follow FCD data model"
            assert (
                len(batch["segmentId"]) == 50
            ), f"Batch {i} should contain 50 segments"

            # Verify segment IDs in each batch
            # Batch 0: blobs 0-49 => times 00:00-00:49 => minutes 0-49 => seg0-seg49
            # Batch 1: blobs 50-99 => times 00:50-01:39 => minutes 50-99 => seg50-seg99
            if i == 0:
                assert "seg0" in batch["segmentId"], "First batch should contain seg0"
                assert "seg49" in batch["segmentId"], "First batch should contain seg49"
            else:
                assert (
                    "seg50" in batch["segmentId"]
                ), "Second batch should contain seg50"
                assert (
                    "seg99" in batch["segmentId"]
                ), "Second batch should contain seg99"

    def test_process_handles_download_failure(self):
        """
        Test that download failures are handled gracefully with REAL error handling.

        Verifies that:
        1. Failed blob downloads are skipped
        2. Processing continues with successful blobs
        3. Batch still yields if any blobs succeed
        """
        azure_manager = MagicMock()

        # Create 2 mock blobs - first fails, second succeeds
        mock_blob1 = MagicMock()
        mock_blob1.name = "fcd_data_2025-01-01T12:00:00.json"
        mock_blob2 = MagicMock()
        mock_blob2.name = "fcd_data_2025-01-01T12:05:00.json"

        azure_manager.get_blobs_in_range.return_value = [mock_blob1, mock_blob2]

        # First download fails (returns None), second succeeds
        def mock_download(blob_name):
            if "12:00:00" in blob_name:
                return None  # Simulated download failure
            return create_tomtom_json_blob(
                segment_id="success_seg", speed=50, confidence=80
            )

        azure_manager.download_blob_content.side_effect = mock_download

        # Execute: NO MOCKING - Real error handling runs
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Should still yield 1 batch (second blob succeeded)
        assert len(results) == 1, "Should process successful blob despite one failure"
        assert (
            "success_seg" in results[0]["segmentId"]
        ), "Should contain the successful segment"

    def test_process_handles_parse_failure(self):
        """
        Test that JSON parse failures are handled gracefully with REAL parsing.

        Verifies invalid JSON is skipped without crashing.
        """
        azure_manager = MagicMock()

        mock_blob = MagicMock()
        mock_blob.name = "fcd_data_20250101_120000.json"
        azure_manager.get_blobs_in_range.return_value = [mock_blob]
        # Return invalid JSON that will fail to parse
        azure_manager.download_blob_content.return_value = b"this is not valid json{"

        # Execute: NO MOCKING - Real JSON parsing error handling runs
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Should yield 0 batches (parse failed, blob skipped)
        assert len(results) == 0, "Invalid JSON should be skipped gracefully"

    def test_process_handles_missing_timestamp(self):
        """
        Test that blobs with invalid filenames are handled gracefully with REAL timestamp extraction.

        Verifies filename without valid timestamp pattern is skipped.
        """
        azure_manager = MagicMock()

        mock_blob = MagicMock()
        mock_blob.name = "invalid_filename_format.json"  # No timestamp pattern
        azure_manager.get_blobs_in_range.return_value = [mock_blob]
        azure_manager.download_blob_content.return_value = create_tomtom_json_blob(
            segment_id="test", speed=50, confidence=80
        )

        # Execute: NO MOCKING - Real timestamp extraction runs
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Should yield 0 batches (no valid timestamp in filename)
        assert len(results) == 0, "Blob with invalid filename should be skipped"

    def test_process_custom_batch_size(self):
        """
        Test that custom batch size is respected with REAL batching logic.

        Verifies smaller batch size correctly divides blobs.
        """
        azure_manager = MagicMock()

        # Create 30 mock blobs with batch_size=10 (should yield 3 batches)
        mock_blobs = []
        for i in range(30):
            mock_blob = MagicMock()
            # Format: YYYY-MM-DDTHH:MM:SS - use sequential times
            hour = 12 + (i // 12)  # 12 blobs per hour
            minute = (i % 12) * 5  # 5-minute intervals within the hour
            mock_blob.name = f"fcd_data_2025-01-01T{hour:02d}:{minute:02d}:00.json"
            mock_blobs.append(mock_blob)

        azure_manager.get_blobs_in_range.return_value = mock_blobs

        # Return realistic TomTom data for each blob
        azure_manager.download_blob_content.return_value = create_tomtom_json_blob(
            segment_id="test_seg", speed=50, confidence=80
        )

        # Execute: NO MOCKING - Real batching with custom size
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=10,  # Custom batch size
            )
        )

        # Assert: Should yield 3 batches (30 blobs / 10 batch_size = 3)
        assert len(results) == 3, "Should respect custom batch_size=10"

        # Each batch should contain exactly 10 segments (all same segment ID in this test)
        for i, batch in enumerate(results):
            assert "segmentId" in batch, f"Batch {i} should follow FCD data model"
            # All blobs have same segment ID, so only 1 unique segment per batch
            # but with 10 timestamps aggregated
            assert len(batch["segmentId"]) == 1, f"Batch {i} should have 1 segment"

    def test_process_aggregates_within_batch(self):
        """
        Test that multiple blobs within a batch are aggregated correctly with REAL aggregation logic.

        This is a critical test that verifies:
        1. Multiple timestamps for the same segment are combined
        2. Different segments are handled independently
        3. Date sorting works correctly
        """
        azure_manager = MagicMock()

        # Create 3 blobs with different timestamps but some shared segment IDs
        mock_blob1 = MagicMock()
        mock_blob1.name = "fcd_data_2025-01-01T12:00:00.json"
        mock_blob2 = MagicMock()
        mock_blob2.name = "fcd_data_2025-01-01T12:05:00.json"
        mock_blob3 = MagicMock()
        mock_blob3.name = "fcd_data_2025-01-01T12:10:00.json"

        azure_manager.get_blobs_in_range.return_value = [
            mock_blob1,
            mock_blob2,
            mock_blob3,
        ]

        # Each blob has data for segments at different timestamps
        def mock_download(blob_name):
            if "12:00:00" in blob_name:
                # First blob: segment A and B
                data = {
                    "detailedSegments": [
                        {
                            "segmentIdStr": "segA",
                            "currentSpeed": 50,
                            "averageSpeed": 55,
                            "typicalSpeed": 60,
                            "confidence": 80,
                            "shape": [
                                {"longitude": 24.9384, "latitude": 60.1699},
                                {"longitude": 24.9394, "latitude": 60.1709},
                            ],
                        },
                        {
                            "segmentIdStr": "segB",
                            "currentSpeed": 40,
                            "averageSpeed": 45,
                            "typicalSpeed": 50,
                            "confidence": 75,
                            "shape": [
                                {"longitude": 24.9400, "latitude": 60.1700},
                                {"longitude": 24.9410, "latitude": 60.1710},
                            ],
                        },
                    ]
                }
            elif "12:05:00" in blob_name:
                # Second blob: segment A again (different timestamp)
                data = {
                    "detailedSegments": [
                        {
                            "segmentIdStr": "segA",
                            "currentSpeed": 52,
                            "averageSpeed": 57,
                            "typicalSpeed": 62,
                            "confidence": 82,
                            "shape": [
                                {"longitude": 24.9384, "latitude": 60.1699},
                                {"longitude": 24.9394, "latitude": 60.1709},
                            ],
                        }
                    ]
                }
            else:  # "12:10:00"
                # Third blob: segment B and C
                data = {
                    "detailedSegments": [
                        {
                            "segmentIdStr": "segB",
                            "currentSpeed": 42,
                            "averageSpeed": 47,
                            "typicalSpeed": 52,
                            "confidence": 77,
                            "shape": [
                                {"longitude": 24.9400, "latitude": 60.1700},
                                {"longitude": 24.9410, "latitude": 60.1710},
                            ],
                        },
                        {
                            "segmentIdStr": "segC",
                            "currentSpeed": 60,
                            "averageSpeed": 65,
                            "typicalSpeed": 70,
                            "confidence": 90,
                            "shape": [
                                {"longitude": 24.9420, "latitude": 60.1720},
                                {"longitude": 24.9430, "latitude": 60.1730},
                            ],
                        },
                    ]
                }
            return json.dumps(data).encode("utf-8")

        azure_manager.download_blob_content.side_effect = mock_download

        # Execute: NO MOCKING - Real aggregation logic runs
        results = list(
            process_date_range_streaming(
                azure_manager,
                datetime(2025, 1, 1, tzinfo=UTC),
                datetime(2025, 1, 2, tzinfo=UTC),
                batch_size=50,
            )
        )

        # Assert: Should yield 1 batch with aggregated data from all blobs
        assert len(results) == 1, "Should aggregate all blobs into one batch"

        batch_data = results[0]
        assert "segmentId" in batch_data

        # Verify all segments are present
        assert "segA" in batch_data["segmentId"], "Segment A should be present"
        assert "segB" in batch_data["segmentId"], "Segment B should be present"
        assert "segC" in batch_data["segmentId"], "Segment C should be present"

        # Verify segment A has 2 timestamps (120000 and 120500)
        seg_a_dates = batch_data["segmentId"]["segA"]["detailedSegment"]["date"]
        assert len(seg_a_dates) == 2, "Segment A should have 2 timestamps aggregated"
        assert "2025-01-01T12:00:00" in seg_a_dates
        assert "2025-01-01T12:05:00" in seg_a_dates
        # Verify speeds for each timestamp
        assert seg_a_dates["2025-01-01T12:00:00"]["properties"]["currentSpeed"] == 50
        assert seg_a_dates["2025-01-01T12:05:00"]["properties"]["currentSpeed"] == 52

        # Verify segment B has 2 timestamps (120000 and 121000)
        seg_b_dates = batch_data["segmentId"]["segB"]["detailedSegment"]["date"]
        assert len(seg_b_dates) == 2, "Segment B should have 2 timestamps aggregated"

        # Verify segment C has 1 timestamp (121000)
        seg_c_dates = batch_data["segmentId"]["segC"]["detailedSegment"]["date"]
        assert len(seg_c_dates) == 1, "Segment C should have 1 timestamp"
        assert "2025-01-01T12:10:00" in seg_c_dates

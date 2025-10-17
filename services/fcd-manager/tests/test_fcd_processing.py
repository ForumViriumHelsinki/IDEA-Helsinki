"""
Tests for streaming FCD blob processing.

This module tests the batch-based streaming approach that processes Azure blobs
in batches instead of loading everything into memory at once.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fcd_processing import process_date_range_streaming


class TestStreamingBlobProcessing:
    """Tests for streaming blob processing functionality."""

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
        """Test processing a single batch of blobs."""
        azure_manager = MagicMock()

        # Mock blob
        mock_blob = MagicMock()
        mock_blob.name = "fcd_data_20250101_120000.json"
        azure_manager.get_blobs_in_range.return_value = [mock_blob]

        # Mock blob content
        blob_content = b'{"segments": [{"id": "segment1", "speed": 50}]}'
        azure_manager.download_blob_content.return_value = blob_content

        # Mock FCD processing functions
        with (
            patch("fcd_processing.FcdUtils") as mock_fcd_utils,
            patch("fcd_processing.TomTomFcdAggregator") as mock_aggregator,
        ):
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = {
                "segments": [{"id": "segment1", "speed": 50}]
            }
            mock_aggregator.transform_single_tomtom_json_data_for_aggregation.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.update_tomtom_json_data_for_aggregation_file.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.sort_tomtom_data_aggregation_file_by_date.return_value = {
                "segment1": {"speed": 50}
            }

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        assert len(results) == 1
        assert results[0] == {"segment1": {"speed": 50}}

    def test_process_multiple_batches(self):
        """Test processing multiple batches of blobs."""
        azure_manager = MagicMock()

        # Create 100 mock blobs (will be processed in 2 batches of 50)
        mock_blobs = []
        for i in range(100):
            mock_blob = MagicMock()
            mock_blob.name = f"fcd_data_20250101_{i:06d}.json"
            mock_blobs.append(mock_blob)

        azure_manager.get_blobs_in_range.return_value = mock_blobs
        azure_manager.download_blob_content.return_value = b'{"segments": []}'

        with (
            patch("fcd_processing.FcdUtils") as mock_fcd_utils,
            patch("fcd_processing.TomTomFcdAggregator") as mock_aggregator,
        ):
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = {"segments": []}
            # Return non-empty data so batches are yielded
            mock_aggregator.transform_single_tomtom_json_data_for_aggregation.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.update_tomtom_json_data_for_aggregation_file.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.sort_tomtom_data_aggregation_file_by_date.return_value = {
                "segment1": {"speed": 50}
            }

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        # Should yield 2 batches (100 blobs / 50 batch_size = 2)
        assert len(results) == 2

    def test_process_handles_download_failure(self):
        """Test that download failures are handled gracefully."""
        azure_manager = MagicMock()

        # Create 2 mock blobs - first fails, second succeeds
        mock_blob1 = MagicMock()
        mock_blob1.name = "fcd_data_20250101_120000.json"
        mock_blob2 = MagicMock()
        mock_blob2.name = "fcd_data_20250101_120500.json"

        azure_manager.get_blobs_in_range.return_value = [mock_blob1, mock_blob2]

        # First download fails, second succeeds
        def mock_download(blob_name):
            if "120000" in blob_name:
                return None  # Simulated failure
            return b'{"segments": []}'

        azure_manager.download_blob_content.side_effect = mock_download

        with (
            patch("fcd_processing.FcdUtils") as mock_fcd_utils,
            patch("fcd_processing.TomTomFcdAggregator") as mock_aggregator,
        ):
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = {"segments": []}
            # Return non-empty data so batch is yielded
            mock_aggregator.transform_single_tomtom_json_data_for_aggregation.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.update_tomtom_json_data_for_aggregation_file.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.sort_tomtom_data_aggregation_file_by_date.return_value = {
                "segment1": {"speed": 50}
            }

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        # Should still yield 1 batch (second blob succeeded)
        assert len(results) == 1

    def test_process_handles_parse_failure(self):
        """Test that JSON parse failures are handled gracefully."""
        azure_manager = MagicMock()

        mock_blob = MagicMock()
        mock_blob.name = "fcd_data_20250101_120000.json"
        azure_manager.get_blobs_in_range.return_value = [mock_blob]
        azure_manager.download_blob_content.return_value = b"invalid json"

        with patch("fcd_processing.FcdUtils") as mock_fcd_utils:
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = None  # Parse failure

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        # Should yield 0 batches (parse failed)
        assert len(results) == 0

    def test_process_handles_missing_timestamp(self):
        """Test that missing timestamp is handled gracefully."""
        azure_manager = MagicMock()

        mock_blob = MagicMock()
        mock_blob.name = "invalid_name.json"
        azure_manager.get_blobs_in_range.return_value = [mock_blob]

        with patch("fcd_processing.FcdUtils") as mock_fcd_utils:
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                None  # Timestamp extraction failed
            )

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        # Should yield 0 batches (no valid timestamp)
        assert len(results) == 0

    def test_process_custom_batch_size(self):
        """Test that custom batch size is respected."""
        azure_manager = MagicMock()

        # Create 30 mock blobs with batch_size=10 (should yield 3 batches)
        mock_blobs = []
        for i in range(30):
            mock_blob = MagicMock()
            mock_blob.name = f"fcd_data_20250101_{i:06d}.json"
            mock_blobs.append(mock_blob)

        azure_manager.get_blobs_in_range.return_value = mock_blobs
        azure_manager.download_blob_content.return_value = b'{"segments": []}'

        with (
            patch("fcd_processing.FcdUtils") as mock_fcd_utils,
            patch("fcd_processing.TomTomFcdAggregator") as mock_aggregator,
        ):
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = {"segments": []}
            # Return non-empty data so batches are yielded
            mock_aggregator.transform_single_tomtom_json_data_for_aggregation.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.update_tomtom_json_data_for_aggregation_file.return_value = {
                "segment1": {"speed": 50}
            }
            mock_aggregator.sort_tomtom_data_aggregation_file_by_date.return_value = {
                "segment1": {"speed": 50}
            }

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=10,
                )
            )

        # Should yield 3 batches (30 blobs / 10 batch_size = 3)
        assert len(results) == 3

    def test_process_aggregates_within_batch(self):
        """Test that multiple blobs within a batch are aggregated correctly."""
        azure_manager = MagicMock()

        # Create 2 blobs with different segment data
        mock_blob1 = MagicMock()
        mock_blob1.name = "fcd_data_20250101_120000.json"
        mock_blob2 = MagicMock()
        mock_blob2.name = "fcd_data_20250101_120500.json"

        azure_manager.get_blobs_in_range.return_value = [mock_blob1, mock_blob2]
        azure_manager.download_blob_content.return_value = b'{"segments": []}'

        with (
            patch("fcd_processing.FcdUtils") as mock_fcd_utils,
            patch("fcd_processing.TomTomFcdAggregator") as mock_aggregator,
        ):
            mock_fcd_utils.extract_timestamp_str_from_file_name.return_value = (
                "2025-01-01T12:00:00"
            )
            mock_fcd_utils.parse_json_from_bytes.return_value = {"segments": []}
            mock_aggregator.transform_single_tomtom_json_data_for_aggregation.return_value = {
                "segment1": {"speed": 50}
            }

            # Mock aggregation to accumulate data
            call_count = {"count": 0}

            def mock_aggregate(new_data, existing_data):
                call_count["count"] += 1
                if call_count["count"] == 1:
                    return {"segment1": {"speed": 50}}
                else:
                    return {"segment1": {"speed": 50}, "segment2": {"speed": 60}}

            mock_aggregator.update_tomtom_json_data_for_aggregation_file.side_effect = (
                mock_aggregate
            )
            mock_aggregator.sort_tomtom_data_aggregation_file_by_date.return_value = {
                "segment1": {"speed": 50},
                "segment2": {"speed": 60},
            }

            results = list(
                process_date_range_streaming(
                    azure_manager,
                    datetime(2025, 1, 1, tzinfo=UTC),
                    datetime(2025, 1, 2, tzinfo=UTC),
                    batch_size=50,
                )
            )

        # Should yield 1 batch with aggregated data from both blobs
        assert len(results) == 1
        assert "segment1" in results[0]
        assert "segment2" in results[0]

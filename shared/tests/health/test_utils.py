"""Unit tests for health check utility functions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from idea_shared.health.utils import check_backfill_mode


class TestCheckBackfillMode:
    """Tests for check_backfill_mode utility function."""

    def test_real_time_mode_with_recent_data(self):
        """Test real-time mode when data is within freshness threshold.

        Verifies that when recent data exists within the configured freshness
        threshold, the function returns real-time mode (backfill_timestamp=None).
        """
        # Mock query API with recent data
        mock_query_api = MagicMock()
        mock_record = MagicMock()
        mock_record.get_time.return_value = datetime.now(UTC)
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        mock_query_api.query.return_value = [mock_table]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is True
        assert age_minutes is not None
        assert age_minutes < 1.0  # Very recent
        assert backfill_ts is None  # Real-time mode

    def test_backfill_mode_with_old_data(self):
        """Test backfill mode when data is older than freshness threshold.

        Verifies that when no recent data exists but old data is found,
        the function returns backfill mode with the old data's timestamp.
        """
        # Mock query API: no recent data, but old data exists
        mock_query_api = MagicMock()
        old_timestamp = datetime.now(UTC) - timedelta(hours=5)
        mock_old_record = MagicMock()
        mock_old_record.get_time.return_value = old_timestamp
        mock_old_table = MagicMock()
        mock_old_table.records = [mock_old_record]

        # First call (recent query) returns empty, second call (latest query) returns old data
        mock_query_api.query.side_effect = [[], [mock_old_table]]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is True
        assert age_minutes is not None
        assert age_minutes > 30  # Older than threshold
        assert backfill_ts == old_timestamp  # Backfill mode with timestamp

    def test_no_data_found(self):
        """Test when no data exists in the lookback window.

        Verifies that when no data is found in either the recent or
        extended lookback window, the function returns no data status.
        """
        # Mock query API returning no data for both queries
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = []

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is False
        assert age_minutes is None
        assert backfill_ts is None

    def test_empty_tables(self):
        """Test when query returns tables with no records.

        Verifies that empty table results are handled correctly,
        treating them as no data found.
        """
        # Mock query API returning tables with no records
        mock_query_api = MagicMock()
        mock_empty_table = MagicMock()
        mock_empty_table.records = []
        mock_query_api.query.return_value = [mock_empty_table]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is False
        assert age_minutes is None
        assert backfill_ts is None

    def test_at_threshold_boundary(self):
        """Test data age exactly at the freshness threshold boundary.

        Verifies that data exactly at the threshold is treated correctly.
        Since the condition is `age > threshold`, data at exactly the
        threshold should be in real-time mode.
        """
        # Mock query API with data exactly at threshold (31 minutes old)
        mock_query_api = MagicMock()
        threshold_timestamp = datetime.now(UTC) - timedelta(minutes=31)
        mock_record = MagicMock()
        mock_record.get_time.return_value = threshold_timestamp
        mock_table = MagicMock()
        mock_table.records = [mock_record]

        # First call returns empty, second call returns threshold data
        mock_query_api.query.side_effect = [[], [mock_table]]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is True
        assert age_minutes > 30
        assert backfill_ts == threshold_timestamp  # Should be in backfill mode

    def test_query_api_exception(self):
        """Test handling of InfluxDB query exceptions.

        Verifies that exceptions from the query API are allowed to
        propagate to the caller for proper error handling.
        """
        # Mock query API that raises an exception
        mock_query_api = MagicMock()
        mock_query_api.query.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            check_backfill_mode(
                query_api=mock_query_api,
                org="test_org",
                bucket="test_bucket",
                measurement="test_measurement",
                freshness_threshold_minutes=30,
                backfill_lookback_days=7,
            )

    def test_multiple_tables_with_data(self):
        """Test handling of multiple tables returned by query.

        Verifies that the function correctly extracts data from the first
        table with records when multiple tables are returned.
        """
        # Mock query API returning multiple tables
        mock_query_api = MagicMock()

        # First table empty, second table has data
        mock_empty_table = MagicMock()
        mock_empty_table.records = []

        mock_data_table = MagicMock()
        mock_record = MagicMock()
        recent_time = datetime.now(UTC)
        mock_record.get_time.return_value = recent_time
        mock_data_table.records = [mock_record]

        mock_query_api.query.return_value = [mock_empty_table, mock_data_table]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is True
        assert age_minutes is not None
        assert backfill_ts is None  # Real-time mode

    def test_record_without_get_time_method(self):
        """Test handling of records without get_time method.

        Verifies that records missing the get_time method are handled
        gracefully and don't cause errors.
        """
        # Mock query API with record that has no get_time
        mock_query_api = MagicMock()
        mock_record = MagicMock()
        del mock_record.get_time  # Remove get_time attribute
        mock_table = MagicMock()
        mock_table.records = [mock_record]

        # First call returns empty, second returns record without get_time
        mock_query_api.query.side_effect = [[], [mock_table]]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        # Should return no data since get_time is missing
        assert has_data is False
        assert age_minutes is None
        assert backfill_ts is None

    def test_custom_lookback_period(self):
        """Test with custom backfill lookback period.

        Verifies that the backfill_lookback_days parameter is correctly
        used in the query construction.
        """
        # Mock query API
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = []

        check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=14,  # Custom 14-day lookback
        )

        # Verify second query call uses 14d lookback
        assert mock_query_api.query.call_count == 2
        second_call = mock_query_api.query.call_args_list[1]
        query_string = second_call[1]["query"]
        assert "-14d" in query_string

    def test_flux_query_parameters(self):
        """Test that Flux queries use correct parameters.

        Verifies that bucket, measurement, and time ranges are correctly
        embedded in the Flux queries sent to InfluxDB.
        """
        # Mock query API
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = []

        check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="fcd_bucket",
            measurement="fcd_data",
            freshness_threshold_minutes=45,
            backfill_lookback_days=10,
        )

        # Verify both queries were called
        assert mock_query_api.query.call_count == 2

        # Check first query (recent data)
        first_call = mock_query_api.query.call_args_list[0]
        first_query = first_call[1]["query"]
        assert "fcd_bucket" in first_query
        assert "fcd_data" in first_query
        assert "-45m" in first_query

        # Check second query (latest data)
        second_call = mock_query_api.query.call_args_list[1]
        second_query = second_call[1]["query"]
        assert "fcd_bucket" in second_query
        assert "fcd_data" in second_query
        assert "-10d" in second_query

    def test_age_calculation_precision(self):
        """Test that age calculation is precise.

        Verifies that the age_minutes calculation correctly converts
        the time difference from seconds to minutes. Uses data that is
        actually within the freshness threshold to properly test real-time mode.
        """
        # Mock query API with data 2 minutes old (within 30-minute threshold)
        mock_query_api = MagicMock()
        two_minutes_ago = datetime.now(UTC) - timedelta(minutes=2)
        mock_record = MagicMock()
        mock_record.get_time.return_value = two_minutes_ago
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        mock_query_api.query.return_value = [mock_table]

        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is True
        assert age_minutes is not None
        # Should be approximately 2 minutes (allow small variance for test execution time)
        assert 1.9 < age_minutes < 2.1
        assert backfill_ts is None  # Recent data, real-time mode

    def test_invalid_bucket_name(self):
        """Test input validation for invalid bucket names.

        Verifies that bucket names with invalid characters (potential
        injection risks) are rejected with a ValueError.
        """
        mock_query_api = MagicMock()

        with pytest.raises(ValueError, match="Invalid bucket name"):
            check_backfill_mode(
                query_api=mock_query_api,
                org="test_org",
                bucket="test; DROP TABLE",  # SQL-injection-like pattern
                measurement="test_measurement",
                freshness_threshold_minutes=30,
                backfill_lookback_days=7,
            )

    def test_invalid_measurement_name(self):
        """Test input validation for invalid measurement names.

        Verifies that measurement names with invalid characters are
        rejected to prevent query injection vulnerabilities.
        """
        mock_query_api = MagicMock()

        with pytest.raises(ValueError, match="Invalid measurement name"):
            check_backfill_mode(
                query_api=mock_query_api,
                org="test_org",
                bucket="test_bucket",
                measurement="test' OR '1'='1",  # Injection pattern
                freshness_threshold_minutes=30,
                backfill_lookback_days=7,
            )

    def test_valid_bucket_with_underscores_and_hyphens(self):
        """Test that valid bucket names with underscores and hyphens are accepted.

        Verifies that the validation allows common valid characters
        (alphanumeric, underscores, hyphens) in bucket names.
        """
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = []

        # Should not raise an exception
        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="fcd_data-bucket",  # Valid name with underscore and hyphen
            measurement="test_measurement",
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is False

    def test_valid_measurement_with_underscores_and_hyphens(self):
        """Test that valid measurement names with underscores and hyphens are accepted.

        Verifies that the validation allows common valid characters
        in measurement names.
        """
        mock_query_api = MagicMock()
        mock_query_api.query.return_value = []

        # Should not raise an exception
        has_data, age_minutes, backfill_ts = check_backfill_mode(
            query_api=mock_query_api,
            org="test_org",
            bucket="test_bucket",
            measurement="fcd-measurement_data",  # Valid name with hyphen and underscore
            freshness_threshold_minutes=30,
            backfill_lookback_days=7,
        )

        assert has_data is False

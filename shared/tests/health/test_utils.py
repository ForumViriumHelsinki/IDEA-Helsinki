import pytest
from unittest.mock import MagicMock
from datetime import datetime, UTC, timedelta
from idea_shared.health.utils import check_backfill_mode

class MockRecord:
    def __init__(self, dt):
        self._dt = dt
    def get_time(self):
        return self._dt

class MockTable:
    def __init__(self, records):
        self.records = records

@pytest.mark.asyncio
async def test_check_backfill_mode_backfill_query():
    # Arrange
    mock_query_api = MagicMock()
    
    # First query (recent) returns empty
    # Second query (latest) returns data from 2 days ago
    past_time = datetime.now(UTC) - timedelta(days=2)
    mock_record = MockRecord(past_time)
    mock_table = MockTable([mock_record])
    
    mock_query_api.query.side_effect = [[], [mock_table]]

    # Act
    has_data, age_minutes, backfill_timestamp = await check_backfill_mode(
        query_api=mock_query_api,
        org="test-org",
        bucket="test-bucket",
        measurement="test-measurement",
        freshness_threshold_minutes=60,
        backfill_lookback_days=7,
    )

    # Assert
    assert has_data is True
    assert age_minutes is not None
    assert backfill_timestamp == past_time
    
    # Verify the generated queries don't use the slow last() aggregate
    assert mock_query_api.query.call_count == 2
    
    recent_query = mock_query_api.query.call_args_list[0].kwargs['query']
    latest_query = mock_query_api.query.call_args_list[1].kwargs['query']
    
    assert '|> last()' not in recent_query
    assert '|> keep(columns: ["_time"])' in recent_query
    assert '|> limit(n: 1)' in recent_query
    
    assert '|> last()' not in latest_query
    assert '|> keep(columns: ["_time"])' in latest_query
    assert '|> limit(n: 1)' in latest_query

@pytest.mark.asyncio
async def test_check_backfill_mode_no_data():
    # Arrange
    mock_query_api = MagicMock()
    mock_query_api.query.side_effect = [[], []]

    # Act
    has_data, age_minutes, backfill_timestamp = await check_backfill_mode(
        query_api=mock_query_api,
        org="test-org",
        bucket="test-bucket",
        measurement="test-measurement",
        freshness_threshold_minutes=60,
        backfill_lookback_days=7,
    )

    # Assert
    assert has_data is False
    assert age_minutes is None
    assert backfill_timestamp is None

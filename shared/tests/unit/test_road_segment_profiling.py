"""Unit tests for orchestrator memory optimizations:
- Chunked 26-week profile queries (Option A)
- Profiling semaphore throttling (Option B)
- Explicit DataFrame cleanup (Option C).

Issue: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/269
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from idea_shared.classes.IdeaHelsinkiRoadSegment import IdeaHelsinkiRoadSegment
from idea_shared.lib.idea.profile.profile import calculate_profile_from_hourly

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(**kwargs) -> IdeaHelsinkiRoadSegment:
    """Create a minimal IdeaHelsinkiRoadSegment for testing."""
    disturbances = [
        {
            "properties": {
                "star_date": "2025-06-01",
                "end_date": "2025-06-30",
            }
        }
    ]
    defaults = {
        "segment_id": "test-segment-001",
        "reported_disturbances": disturbances,
        "validation_frequency": 5,
        "profile_time_frame_weeks": 26,
        "profile_end_lead_time_hours": 0,
        "db_org": "test-org",
        "db_url": "http://localhost:8086",
        "db_fcd_bucket": "fcd-data",
        "db_fcd_token": "test-token",
        "db_validation_bucket": "validation",
        "db_validation_token": "test-token",
    }
    defaults.update(kwargs)
    return IdeaHelsinkiRoadSegment(**defaults)  # ty: ignore[invalid-argument-type]


def _make_hourly_df(n_weeks: int = 4) -> pd.DataFrame:
    """Build a synthetic hourly DataFrame matching the output of ``aggregate_by_hour``.
    Covers ``n_weeks`` of hourly records with non-zero fcd values.
    """
    start = datetime(2025, 1, 1, tzinfo=UTC)
    hours = n_weeks * 7 * 24
    index = pd.date_range(start=start, periods=hours, freq="h", tz=UTC)
    df = pd.DataFrame(
        {
            "hour_of_date": index,
            "fcd_mean": [5.0] * hours,
            "max_consecutive_zeros": [2] * hours,
            "max_consecutive_zeros_or_ones": [3] * hours,
        }
    )
    return df


# ---------------------------------------------------------------------------
# Tests for calculate_profile_from_hourly
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculateProfileFromHourly:
    """Tests for the new calculate_profile_from_hourly function."""

    def test_returns_dataframe_with_required_columns(self):
        """Profile output must have day_of_week, hour_of_day, and metric columns."""
        hourly_df = _make_hourly_df(n_weeks=26)
        profile = calculate_profile_from_hourly(hourly_df, minimum_weeks_required=10)

        assert isinstance(profile, pd.DataFrame)
        assert "day_of_week" in profile.columns
        assert "hour_of_day" in profile.columns
        assert "fcd_mean_median" in profile.columns
        assert "max_consecutive_zeros_q95" in profile.columns
        assert "max_consecutive_zeros_or_ones_q95" in profile.columns

    def test_profile_has_at_most_168_rows(self):
        """A profile aggregates to at most 7 days × 24 hours = 168 rows."""
        hourly_df = _make_hourly_df(n_weeks=26)
        profile = calculate_profile_from_hourly(hourly_df, minimum_weeks_required=10)
        assert len(profile) <= 168

    def test_sorts_input_before_processing(self):
        """Out-of-order hourly data should produce the same result as sorted data."""
        hourly_df = _make_hourly_df(n_weeks=26)
        shuffled = hourly_df.sample(frac=1, random_state=42).reset_index(drop=True)

        profile_sorted = calculate_profile_from_hourly(
            hourly_df, minimum_weeks_required=10
        )
        profile_shuffled = calculate_profile_from_hourly(
            shuffled, minimum_weeks_required=10
        )

        pd.testing.assert_frame_equal(
            profile_sorted.sort_values(["day_of_week", "hour_of_day"]).reset_index(
                drop=True
            ),
            profile_shuffled.sort_values(["day_of_week", "hour_of_day"]).reset_index(
                drop=True
            ),
        )

    def test_empty_hourly_df_raises_idea_error(self):
        """An empty DataFrame should eventually raise IDEAError from does_profile_has_enough_data."""
        from idea_shared.lib.idea.exceptions import IDEAError

        empty = pd.DataFrame(
            columns=[
                "hour_of_date",
                "fcd_mean",
                "max_consecutive_zeros",
                "max_consecutive_zeros_or_ones",
            ]
        )
        with pytest.raises(IDEAError):
            calculate_profile_from_hourly(empty, minimum_weeks_required=1)


# ---------------------------------------------------------------------------
# Tests for IdeaHelsinkiRoadSegment.__get_hourly_profile_data (chunked queries)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChunkedProfileDataFetching:
    """Tests for chunked 26-week data retrieval with pre-aggregation."""

    def _make_raw_chunk_df(self, start: datetime, end: datetime) -> pd.DataFrame:
        """Build a minimal raw segment DataFrame (index = DatetimeIndex)."""
        idx = pd.date_range(start=start, end=end, freq="5min", tz=UTC)
        return pd.DataFrame({"fcd": [5] * len(idx)}, index=idx)

    @pytest.mark.asyncio
    async def test_chunked_query_calls_influxdb_multiple_times(self):
        """A 26-week window should result in multiple InfluxDB calls (~7 chunks)."""
        segment = _make_segment()

        call_count = 0

        async def fake_fetch(segment_id, start_time, end_time):
            nonlocal call_count
            call_count += 1
            return self._make_raw_chunk_df(start_time, end_time)

        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_fetch  # ty: ignore[unresolved-attribute]

        result = await segment._IdeaHelsinkiRoadSegment__get_hourly_profile_data()  # ty: ignore[unresolved-attribute]

        assert result is not None
        assert not result.empty
        # 26 weeks / 4-week chunks = 7 calls (6 full + 1 partial or 7)
        assert call_count >= 6, f"Expected ≥6 chunk calls, got {call_count}"

    @pytest.mark.asyncio
    async def test_chunked_result_has_hourly_columns(self):
        """Pre-aggregated result must have aggregate_by_hour output columns."""
        segment = _make_segment()

        async def fake_fetch(segment_id, start_time, end_time):
            return self._make_raw_chunk_df(start_time, end_time)

        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_fetch  # ty: ignore[unresolved-attribute]

        result = await segment._IdeaHelsinkiRoadSegment__get_hourly_profile_data()  # ty: ignore[unresolved-attribute]

        assert result is not None
        assert "hour_of_date" in result.columns
        assert "fcd_mean" in result.columns
        assert "max_consecutive_zeros" in result.columns
        assert "max_consecutive_zeros_or_ones" in result.columns

    @pytest.mark.asyncio
    async def test_returns_none_when_all_chunks_empty(self):
        """Returns None when all InfluxDB chunk calls return empty/None data."""
        segment = _make_segment()

        async def fake_fetch_empty(segment_id, start_time, end_time):
            return None

        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_fetch_empty  # ty: ignore[unresolved-attribute]

        result = await segment._IdeaHelsinkiRoadSegment__get_hourly_profile_data()  # ty: ignore[unresolved-attribute]

        assert result is None

    @pytest.mark.asyncio
    async def test_hourly_rows_much_fewer_than_raw_rows(self):
        """After pre-aggregation, hourly row count should be ~12× less than raw data."""
        segment = _make_segment(profile_time_frame_weeks=4)

        raw_rows = []

        async def fake_fetch(segment_id, start_time, end_time):
            df = self._make_raw_chunk_df(start_time, end_time)
            raw_rows.append(len(df))
            return df

        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_fetch  # ty: ignore[unresolved-attribute]

        result = await segment._IdeaHelsinkiRoadSegment__get_hourly_profile_data()  # ty: ignore[unresolved-attribute]

        assert result is not None
        total_raw = sum(raw_rows)
        hourly_count = len(result)
        # Expect at least 8× reduction (5-min → hourly = 12× theoretical)
        assert hourly_count < total_raw / 8, (
            f"Expected hourly rows ({hourly_count}) to be much fewer than raw rows ({total_raw})"
        )


# ---------------------------------------------------------------------------
# Tests for profiling semaphore throttling (Option B)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProfilingSemaphore:
    """Tests for the asyncio.Semaphore that limits concurrent profile queries."""

    def test_segment_stores_provided_semaphore(self):
        """Segment should store the semaphore passed at construction."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(profiling_semaphore=sem)
        assert segment.profiling_semaphore is sem

    def test_segment_stores_none_semaphore_by_default(self):
        """Default semaphore should be None (no throttling)."""
        segment = _make_segment()
        assert segment.profiling_semaphore is None

    @pytest.mark.asyncio
    async def test_semaphore_acquired_during_profiling(self):
        """The semaphore should be acquired while the profile query runs."""
        sem = asyncio.Semaphore(3)
        acquired_during_call = False
        segment = _make_segment(profiling_semaphore=sem)

        # Patch out the hourly fetch and profile calculation
        async def fake_get_hourly():
            nonlocal acquired_during_call
            # If semaphore is acquired, its internal counter is decremented
            acquired_during_call = sem._value < 3
            return None  # Return None to short-circuit profiling

        with patch.object(
            segment,
            "_IdeaHelsinkiRoadSegment__get_hourly_profile_data",
            side_effect=fake_get_hourly,
        ):
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert acquired_during_call, "Semaphore was not acquired during profiling"

    @pytest.mark.asyncio
    async def test_semaphore_released_after_profiling(self):
        """The semaphore must be fully released after profiling completes."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(profiling_semaphore=sem)

        async def fake_get_hourly():
            return None

        with patch.object(
            segment,
            "_IdeaHelsinkiRoadSegment__get_hourly_profile_data",
            side_effect=fake_get_hourly,
        ):
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert sem._value == 3, "Semaphore not fully released after profiling"

    @pytest.mark.asyncio
    async def test_semaphore_released_even_on_error(self):
        """The semaphore must be released even if an IDEAError is raised."""
        from idea_shared.lib.idea.exceptions import IDEAError

        sem = asyncio.Semaphore(3)
        segment = _make_segment(profiling_semaphore=sem)

        # Hourly data exists but calculate_profile_from_hourly raises IDEAError
        hourly_df = _make_hourly_df(n_weeks=4)

        async def fake_get_hourly():
            return hourly_df

        with (
            patch.object(
                segment,
                "_IdeaHelsinkiRoadSegment__get_hourly_profile_data",
                side_effect=fake_get_hourly,
            ),
            patch(
                "idea_shared.classes.IdeaHelsinkiRoadSegment.calculate_profile_from_hourly",
                side_effect=IDEAError("not enough data"),
            ),
        ):
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert sem._value == 3, (
            "Semaphore not released after IDEAError during profiling"
        )


# ---------------------------------------------------------------------------
# Tests for IdeaHelsinkiManager semaphore creation and passing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManagerProfilingSemaphore:
    """Tests that the manager creates and shares the semaphore."""

    def _make_manager(self):
        from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager

        return IdeaHelsinkiManager(
            validation_frequency=5,
            profile_time_frame_weeks=26,
            profile_end_lead_time_hours=0,
            validation_max_age_days=7,
            validation_history_weeks=4,
            traffic_disturbance_data_file_location="/tmp/test.json",
            traffic_disturbance_update_frequency=60,
            db_org="test-org",
            db_url="http://localhost:8086",
            db_fcd_bucket="fcd-data",
            db_fcd_token="test-token",
            db_validation_bucket="validation",
            db_validation_token="test-token",
        )

    def test_manager_creates_profiling_semaphore(self):
        """Manager must create a Semaphore(3) on init."""
        manager = self._make_manager()
        assert isinstance(manager._profiling_semaphore, asyncio.Semaphore)
        assert manager._profiling_semaphore._value == 3

    @pytest.mark.asyncio
    async def test_manager_passes_semaphore_to_new_segments(self):
        """New segments created by the manager must share the manager's semaphore."""
        manager = self._make_manager()

        disturbance_data = {
            "segmentId": {
                "seg-001": {
                    "detailedCollisions": [
                        {
                            "properties": {
                                "star_date": "2025-06-01",
                                "end_date": "2025-06-30",
                            }
                        }
                    ]
                }
            }
        }

        with patch.object(
            manager, "_get_disturbance_data", return_value=disturbance_data
        ):
            with patch("asyncio.create_task", return_value=MagicMock()):
                await manager._run_management_cycle_with_error_isolation()

        seg = manager.active_segments["seg-001"]["instance"]
        assert seg.profiling_semaphore is manager._profiling_semaphore

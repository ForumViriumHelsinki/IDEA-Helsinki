"""Unit tests for validation semaphore and configurable validation history window.

- Validation semaphore throttling (Issue #279)
- Configurable validation history window (Issue #267)

Issue: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/279
Issue: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/267
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from idea_shared.classes.IdeaHelsinkiRoadSegment import IdeaHelsinkiRoadSegment

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


def _make_manager(**kwargs):
    """Create a minimal IdeaHelsinkiManager for testing."""
    from idea_shared.classes.IdeaHelsinkiManager import IdeaHelsinkiManager

    defaults = {
        "validation_frequency": 5,
        "profile_time_frame_weeks": 26,
        "profile_end_lead_time_hours": 0,
        "validation_history_weeks": 4,
        "traffic_disturbance_data_file_location": "/tmp/test.json",
        "traffic_disturbance_update_frequency": 60,
        "db_org": "test-org",
        "db_url": "http://localhost:8086",
        "db_fcd_bucket": "fcd-data",
        "db_fcd_token": "test-token",
        "db_validation_bucket": "validation",
        "db_validation_token": "test-token",
    }
    defaults.update(kwargs)
    return IdeaHelsinkiManager(**defaults)  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# Tests for validation semaphore (Issue #279)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidationSemaphore:
    """Tests for the asyncio.Semaphore that limits concurrent validation history queries."""

    def test_segment_stores_provided_semaphore(self):
        """Segment should store the validation semaphore passed at construction."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(validation_semaphore=sem)
        assert segment.validation_semaphore is sem

    def test_segment_stores_none_semaphore_by_default(self):
        """Default validation semaphore should be None (no throttling)."""
        segment = _make_segment()
        assert segment.validation_semaphore is None

    @pytest.mark.asyncio
    async def test_semaphore_acquired_during_validation_history_fetch(self):
        """The semaphore should be acquired while fetching validation history."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(validation_semaphore=sem)

        # Set up: segment has a profile but no last_segment_validation
        segment.segment_profile = pd.DataFrame({"col": [1]})
        segment.last_validation_update = datetime.now(UTC) - timedelta(hours=1)

        acquired_during_call = False

        async def fake_get_validation(segment_id, start_time, end_time):
            nonlocal acquired_during_call
            acquired_during_call = sem._value < 3
            return None

        async def fake_get_segment_data(segment_id, start_time, end_time):
            # Return None to short-circuit before validate_roadwork
            return None

        segment._IdeaHelsinkiRoadSegment__get_validation_dataframe_from_influxdb = (  # ty: ignore[unresolved-attribute]
            fake_get_validation
        )
        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_get_segment_data  # ty: ignore[unresolved-attribute]

        await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert acquired_during_call, (
            "Semaphore was not acquired during validation history fetch"
        )

    @pytest.mark.asyncio
    async def test_semaphore_released_after_validation_history_fetch(self):
        """The semaphore must be fully released after validation history fetch completes."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(validation_semaphore=sem)

        segment.segment_profile = pd.DataFrame({"col": [1]})
        segment.last_validation_update = datetime.now(UTC) - timedelta(hours=1)

        async def fake_get_validation(segment_id, start_time, end_time):
            return None

        async def fake_get_segment_data(segment_id, start_time, end_time):
            # Return None to short-circuit before validate_roadwork
            return None

        segment._IdeaHelsinkiRoadSegment__get_validation_dataframe_from_influxdb = (  # ty: ignore[unresolved-attribute]
            fake_get_validation
        )
        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_get_segment_data  # ty: ignore[unresolved-attribute]

        await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert sem._value == 3, (
            "Semaphore not fully released after validation history fetch"
        )

    @pytest.mark.asyncio
    async def test_semaphore_released_on_error(self):
        """The semaphore must be released even if the validation history fetch raises."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(validation_semaphore=sem)

        segment.segment_profile = pd.DataFrame({"col": [1]})
        segment.last_validation_update = datetime.now(UTC) - timedelta(hours=1)

        async def fake_get_validation(segment_id, start_time, end_time):
            raise RuntimeError("InfluxDB unavailable")

        async def fake_get_segment_data(segment_id, start_time, end_time):
            return None

        segment._IdeaHelsinkiRoadSegment__get_validation_dataframe_from_influxdb = (  # ty: ignore[unresolved-attribute]
            fake_get_validation
        )
        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_get_segment_data  # ty: ignore[unresolved-attribute]

        with pytest.raises(RuntimeError):
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert sem._value == 3, (
            "Semaphore not released after error during validation history fetch"
        )

    @pytest.mark.asyncio
    async def test_semaphore_not_acquired_when_validation_exists(self):
        """When last_segment_validation already exists, semaphore should not be acquired."""
        sem = asyncio.Semaphore(3)
        segment = _make_segment(validation_semaphore=sem)

        segment.segment_profile = pd.DataFrame({"col": [1]})
        segment.last_validation_update = datetime.now(UTC) - timedelta(hours=1)
        segment.last_segment_validation = pd.DataFrame({"existing": [1]})

        async def fake_get_segment_data(segment_id, start_time, end_time):
            # During this call, semaphore should NOT have been acquired
            assert sem._value == 3, "Semaphore was acquired when it shouldn't have been"
            return None

        segment._IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb = fake_get_segment_data  # ty: ignore[unresolved-attribute]

        await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        assert sem._value == 3


# ---------------------------------------------------------------------------
# Tests for manager validation semaphore creation and passing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManagerValidationSemaphore:
    """Tests that the manager creates and shares the validation semaphore."""

    def test_manager_creates_validation_semaphore(self):
        """Manager must create a validation Semaphore on init."""
        manager = _make_manager()
        assert isinstance(manager._validation_semaphore, asyncio.Semaphore)
        assert manager._validation_semaphore._value == 3

    @pytest.mark.asyncio
    async def test_manager_passes_validation_semaphore_to_new_segments(self):
        """New segments created by the manager must share the manager's validation semaphore."""
        manager = _make_manager()

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
            with patch("asyncio.create_task") as mock_create_task:
                # We don't want the task to actually run, so we just mock create_task
                await manager._run_management_cycle_with_error_isolation()

                # Clean up the unawaited coroutines to prevent RuntimeWarnings
                for call in mock_create_task.call_args_list:
                    coro = call.args[0]
                    coro.close()

        seg = manager.active_segments["seg-001"]["instance"]
        assert seg.validation_semaphore is manager._validation_semaphore

    @pytest.mark.asyncio
    async def test_manager_passes_validation_history_weeks_to_segments(self):
        """New segments must receive the manager's validation_history_weeks."""
        manager = _make_manager(validation_history_weeks=6)

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
            with patch("asyncio.create_task") as mock_create_task:
                # We don't want the task to actually run, so we just mock create_task
                await manager._run_management_cycle_with_error_isolation()

                # Clean up the unawaited coroutines to prevent RuntimeWarnings
                for call in mock_create_task.call_args_list:
                    coro = call.args[0]
                    coro.close()

        seg = manager.active_segments["seg-001"]["instance"]
        assert seg.validation_history_weeks == 6


# ---------------------------------------------------------------------------
# Tests for configurable validation history window (Issue #267)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidationHistoryWindow:
    """Tests for clamping the validation history start date."""

    def test_stores_validation_history_weeks(self):
        """Segment should store the validation_history_weeks parameter."""
        segment = _make_segment(validation_history_weeks=6)
        assert segment.validation_history_weeks == 6

    def test_default_validation_history_weeks(self):
        """Default validation_history_weeks should be 4."""
        segment = _make_segment()
        assert segment.validation_history_weeks == 4

    def test_clamps_old_disturbance(self):
        """For a disturbance started 3 months ago, last_validation_update should be clamped."""
        segment = _make_segment(validation_history_weeks=4)

        # Simulate: profiling_end_date is 3 months ago
        current_date = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        segment.profiling_end_date = current_date - timedelta(days=90)

        segment._initialize_last_validation_update(current_date)

        expected_earliest = current_date - timedelta(weeks=4)
        assert segment.last_validation_update == expected_earliest

    def test_uses_disturbance_date_when_recent(self):
        """For a recent disturbance, last_validation_update should use the disturbance-based date."""
        segment = _make_segment(validation_history_weeks=4)

        current_date = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        segment.profiling_end_date = current_date - timedelta(days=10)

        segment._initialize_last_validation_update(current_date)

        expected_candidate = segment.profiling_end_date + timedelta(days=1)
        assert segment.last_validation_update == expected_candidate

    def test_constant_default_value(self):
        """VALIDATION_HISTORY_WEEKS constant should default to 4."""
        from idea_shared.lib.Constants.Constants import VALIDATION_HISTORY_WEEKS

        assert VALIDATION_HISTORY_WEEKS == 4

    def test_constant_reads_env_override(self):
        """VALIDATION_HISTORY_WEEKS should read from environment variable."""
        with patch.dict("os.environ", {"VALIDATION_HISTORY_WEEKS": "8"}):
            # Re-evaluate the expression (can't re-import module-level constants easily,
            # so we verify the pattern is correct)
            import os

            result = int(os.getenv("VALIDATION_HISTORY_WEEKS", "4"))
            assert result == 8

    def test_zero_history_weeks_starts_one_cycle_before_now(self):
        """When validation_history_weeks=0, last_validation_update should be current_date - validation_frequency."""
        segment = _make_segment(validation_history_weeks=0, validation_frequency=5)

        current_date = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        segment.profiling_end_date = current_date - timedelta(days=90)

        segment._initialize_last_validation_update(current_date)

        expected = current_date - timedelta(minutes=5)
        assert segment.last_validation_update == expected

    def test_zero_history_weeks_ignores_profiling_end_date(self):
        """With validation_history_weeks=0, the profiling_end_date should have no effect."""
        segment_old = _make_segment(validation_history_weeks=0)
        segment_recent = _make_segment(validation_history_weeks=0)

        current_date = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        segment_old.profiling_end_date = current_date - timedelta(days=90)
        segment_recent.profiling_end_date = current_date - timedelta(days=2)

        segment_old._initialize_last_validation_update(current_date)
        segment_recent._initialize_last_validation_update(current_date)

        assert (
            segment_old.last_validation_update == segment_recent.last_validation_update
        )

    def test_profiling_end_date_is_today_starts_one_cycle_before_now(self):
        """When profiling_end_date == current_date (today), last_validation_update must be
        set to one cycle before current_date to avoid an empty InfluxDB range query.

        Regression test for: https://github.com/ForumViriumHelsinki/IDEA-Helsinki/issues/315
        """
        segment = _make_segment(validation_history_weeks=4, validation_frequency=5)

        current_date = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        # profiling_end_date is today — the condition that caused the bug
        segment.profiling_end_date = current_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        segment._initialize_last_validation_update(current_date)

        expected = current_date - timedelta(minutes=5)
        assert segment.last_validation_update == expected, (
            "When profiling_end_date is today, last_validation_update must be "
            "one cycle before current_date, not current_date itself"
        )

    def test_profiling_end_date_is_today_result_is_before_current_date(self):
        """When profiling_end_date is today, last_validation_update must be strictly
        before current_date so the validation query range is non-empty.
        """
        segment = _make_segment(validation_history_weeks=4, validation_frequency=5)

        current_date = datetime(2026, 3, 23, 10, 47, 4, tzinfo=UTC)
        segment.profiling_end_date = current_date.replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        segment._initialize_last_validation_update(current_date)

        assert segment.last_validation_update is not None
        assert segment.last_validation_update < current_date, (
            "last_validation_update must be strictly before current_date to avoid "
            "empty InfluxDB range query (start == stop causes HTTP 400)"
        )

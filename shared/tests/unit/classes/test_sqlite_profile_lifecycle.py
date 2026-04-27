"""Unit tests for SQLite profile lazy-loading and lifecycle management.

Verifies Phase 4 requirements:
- Profiles are serialized to Parquet and saved to SQLite.
- Profiles are dropped from RAM after generation/validation.
- Legacy fallback: In-memory dictionary is used when SQLite is disabled.
- Profiles are deleted from SQLite when invalidated.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from idea_shared.classes.IdeaHelsinkiRoadSegment import IdeaHelsinkiRoadSegment
from idea_shared.data.profile_serialization import serialize_profile
from idea_shared.data.repositories import ProfileRepository


def _make_segment(profile_repo=None) -> IdeaHelsinkiRoadSegment:
    """Create a minimal IdeaHelsinkiRoadSegment for testing."""
    return IdeaHelsinkiRoadSegment(
        segment_id="123",
        reported_disturbances=[],
        validation_frequency=5,
        profile_time_frame_weeks=26,
        profile_end_lead_time_hours=48,
        db_org="test",
        db_url="http://test",
        db_fcd_bucket="test",
        db_fcd_token="test",
        db_validation_bucket="test",
        db_validation_token="test",
        profile_repository=profile_repo,
    )


def _create_dummy_df() -> pd.DataFrame:
    return pd.DataFrame({"test": [1, 2, 3]})


@pytest.fixture
def mock_profile_repo():
    repo = MagicMock(spec=ProfileRepository)
    repo.get_profile.return_value = None
    return repo


class TestSQLiteProfileLifecycle:
    @pytest.mark.asyncio
    @patch(
        "idea_shared.classes.IdeaHelsinkiRoadSegment.IdeaHelsinkiRoadSegment._IdeaHelsinkiRoadSegment__get_hourly_profile_data",
        new_callable=AsyncMock,
    )
    @patch("idea_shared.classes.IdeaHelsinkiRoadSegment.calculate_profile_from_hourly")
    async def test_generation_saves_to_sqlite_and_drops_memory(
        self, mock_calculate, mock_get_hourly, mock_profile_repo
    ):
        """Test: Newly generated profiles are saved to SQLite and dropped from RAM."""
        # Setup mocks
        dummy_df = _create_dummy_df()
        mock_get_hourly.return_value = dummy_df
        mock_calculate.return_value = dummy_df

        segment = _make_segment(profile_repo=mock_profile_repo)

        # Override the validation check to prevent it from going past generation
        with patch.object(
            segment,
            "_IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb",
            new_callable=AsyncMock,
        ) as mock_get_val:
            mock_get_val.return_value = None
            segment.last_validation_update = datetime.now(UTC)

            # Execute the private validation method which contains the lifecycle
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        # Assertions
        # 1. It generated the profile
        mock_calculate.assert_called_once()
        # 2. It saved it to the repository
        mock_profile_repo.save_profile.assert_called_once()
        kwargs = mock_profile_repo.save_profile.call_args.kwargs
        assert kwargs["segment_id"] == "123"
        assert isinstance(kwargs["profile_data"], bytes)
        # 3. It explicitly dropped it from RAM
        assert segment.segment_profile is None

    @pytest.mark.asyncio
    @patch(
        "idea_shared.classes.IdeaHelsinkiRoadSegment.IdeaHelsinkiRoadSegment._IdeaHelsinkiRoadSegment__get_hourly_profile_data",
        new_callable=AsyncMock,
    )
    @patch("idea_shared.classes.IdeaHelsinkiRoadSegment.calculate_profile_from_hourly")
    async def test_legacy_fallback_keeps_in_memory(
        self, mock_calculate, mock_get_hourly
    ):
        """Test: If SQLite is disabled (repo=None), profiles stay in RAM."""
        dummy_df = _create_dummy_df()
        mock_get_hourly.return_value = dummy_df
        mock_calculate.return_value = dummy_df

        # No repository provided
        segment = _make_segment(profile_repo=None)

        with patch.object(
            segment,
            "_IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb",
            new_callable=AsyncMock,
        ) as mock_get_val:
            mock_get_val.return_value = None
            segment.last_validation_update = datetime.now(UTC)
            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        # Assertions
        mock_calculate.assert_called_once()
        # In legacy mode, it MUST assign it to RAM
        assert segment.segment_profile is not None
        pd.testing.assert_frame_equal(segment.segment_profile, dummy_df)

    @pytest.mark.asyncio
    @patch(
        "idea_shared.classes.IdeaHelsinkiRoadSegment.IdeaHelsinkiRoadSegment._IdeaHelsinkiRoadSegment__get_hourly_profile_data",
        new_callable=AsyncMock,
    )
    @patch("idea_shared.classes.IdeaHelsinkiRoadSegment.validate_roadwork")
    async def test_lazy_loading_fetches_from_sqlite(
        self, mock_validate, mock_get_hourly, mock_profile_repo
    ):
        """Test: Validations fetch the profile from SQLite if it exists."""
        dummy_df = _create_dummy_df()

        # Make the repo return an existing profile
        mock_profile_repo.get_profile.return_value = serialize_profile(dummy_df)

        segment = _make_segment(profile_repo=mock_profile_repo)

        with patch.object(
            segment,
            "_IdeaHelsinkiRoadSegment__get_idea_formated_segment_data_from_influxdb",
            new_callable=AsyncMock,
        ) as mock_get_val:
            # Provide dummy FCD data so it triggers the validation block
            mock_get_val.return_value = dummy_df
            segment.last_validation_update = datetime.now(UTC)

            await segment._IdeaHelsinkiRoadSegment__validate_segment(datetime.now(UTC))  # ty: ignore[unresolved-attribute]

        # Assertions
        # 1. It should NEVER generate a new profile because it found it in DB
        mock_get_hourly.assert_not_called()

        # 2. It fetched it from the repo
        mock_profile_repo.get_profile.assert_called_with("123")

        # 3. It passed the deserialized profile into the validation function
        mock_validate.assert_called_once()
        passed_profile = mock_validate.call_args.kwargs["profile"]
        pd.testing.assert_frame_equal(passed_profile, dummy_df)

        # 4. It deleted the active profile from memory afterward (active_profile is scoped)
        assert segment.segment_profile is None

    @pytest.mark.asyncio
    async def test_update_segment_deletes_profile_from_sqlite(self, mock_profile_repo):
        """Test: Changing disturbance dates deletes the old profile from SQLite."""
        segment = _make_segment(profile_repo=mock_profile_repo)

        # Set initial dates to something old
        old_date = datetime(2025, 1, 1, tzinfo=UTC)
        segment.disturbance_start_date = old_date
        segment.disturbance_end_date = old_date

        # Create a mock reported disturbance that will trigger a date change
        new_disturbances = [
            {"properties": {"tyo_alkaa": "2025-05-05", "tyo_paattyy": "2025-06-06"}}
        ]

        # Call update
        await segment.update_segment(new_disturbances)

        # Assertion: It must have deleted the old profile to force regeneration
        mock_profile_repo.delete_profile.assert_called_once_with("123")
        assert segment.segment_profile is None

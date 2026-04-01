"""Tests for SqliteHealthCheck."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from idea_shared.health.idea_checks import SqliteHealthCheck


@pytest.fixture
def populated_db(tmp_path):
    """Create a SQLite database with test tables and data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE segments (id TEXT PRIMARY KEY, data TEXT)")
    conn.execute("CREATE TABLE disturbances (id TEXT PRIMARY KEY, data TEXT)")
    conn.execute("INSERT INTO segments VALUES ('seg_001', '{}')")
    conn.execute("INSERT INTO segments VALUES ('seg_002', '{}')")
    conn.execute("INSERT INTO disturbances VALUES ('dist_001', '{}')")
    conn.commit()
    conn.close()
    return db_path


class TestSqliteHealthCheck:
    """Tests for SqliteHealthCheck."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_healthy_with_populated_database(self, populated_db):
        """Returns healthy when db exists with expected tables."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=populated_db,
            expected_tables=["segments", "disturbances"],
        )
        result = await check.check()

        assert result.status == "healthy"
        assert result.metadata is not None
        assert result.metadata["table_count"] >= 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unhealthy_when_file_missing(self, tmp_path):
        """Returns unhealthy when database file does not exist."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=tmp_path / "nonexistent.db",
            expected_tables=["segments"],
        )
        result = await check.check()

        assert result.status == "unhealthy"
        assert result.message is not None
        assert "not found" in result.message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unhealthy_when_tables_missing(self, populated_db):
        """Returns unhealthy when expected tables are not present."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=populated_db,
            expected_tables=["segments", "nonexistent_table"],
        )
        result = await check.check()

        assert result.status == "unhealthy"
        assert result.message is not None
        assert "nonexistent_table" in result.message
        assert result.metadata is not None
        assert "nonexistent_table" in result.metadata["missing_tables"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_degraded_when_row_count_below_threshold(self, populated_db):
        """Returns degraded when row count is below minimum threshold."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=populated_db,
            expected_tables=["segments", "disturbances"],
            min_row_counts={"segments": 100},
        )
        result = await check.check()

        assert result.status == "degraded"
        assert result.message is not None
        assert "below threshold" in result.message
        assert result.metadata is not None
        assert result.metadata["row_counts"]["segments"] == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_healthy_when_row_count_meets_threshold(self, populated_db):
        """Returns healthy when row count meets minimum threshold."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=populated_db,
            expected_tables=["segments"],
            min_row_counts={"segments": 2},
        )
        result = await check.check()

        assert result.status == "healthy"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_startup_grace_period(self, tmp_path):
        """Returns healthy during startup grace period even if db is missing."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=tmp_path / "nonexistent.db",
            expected_tables=["segments"],
            startup_grace_minutes=10,
        )
        result = await check.check()

        assert result.status == "healthy"
        assert result.message is not None
        assert "grace period" in result.message.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_grace_period_expired_checks_normally(self, tmp_path):
        """After grace period expires, performs normal check."""
        check = SqliteHealthCheck(
            name="test_sqlite",
            db_path=tmp_path / "nonexistent.db",
            expected_tables=["segments"],
            startup_grace_minutes=0,
        )
        # Force startup time to the past
        check._startup_time = datetime.now(UTC) - timedelta(minutes=1)
        result = await check.check()

        assert result.status == "unhealthy"

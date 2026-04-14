"""Unit tests for ``InfluxDBSegmentMigrator``.

These tests mock ``FCDInfluxDBManager`` and assert the migrator issues the
expected Flux queries and only deletes after successful verification.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from idea_shared.classes.InfluxDBSegmentMigrator import (
    BucketTarget,
    migrate_segment_timeseries,
)


def _make_manager(counts: list[int]):
    """Build a mock FCDInfluxDBManager whose count queries return ``counts``.

    ``counts`` is consumed in order: first call returns counts[0], etc.
    Re-tag queries (no count) are swallowed. The Flux text is inspected to
    route count-vs-retag calls.
    """
    manager = MagicMock()
    manager.bucket = "test-bucket"
    manager.org = "test-org"

    call_iter = iter(counts)

    def fake_query(query: str, org: str):  # noqa: ARG001
        if "count(" in query:
            try:
                value = next(call_iter)
            except StopIteration:
                value = 0
            table = MagicMock()
            record = MagicMock()
            record.values = {"_time": value}
            table.records = [record]
            return [table]
        # retag (set + to) returns nothing meaningful
        return []

    manager.query_api.query.side_effect = fake_query
    manager.delete_api.return_value = MagicMock()
    return manager


def test_migration_happy_path_retags_verifies_and_deletes():
    manager = _make_manager(counts=[100, 100])
    target = BucketTarget(manager=manager, measurement="segment_data")

    result = migrate_segment_timeseries("OLD", "NEW", [target])

    assert len(result.targets) == 1
    tr = result.targets[0]
    assert tr.original_count == 100
    assert tr.retagged_count == 100
    assert tr.deleted is True

    # Expect three query calls: count(old) → retag → count(new)
    queries = [
        c.kwargs.get("query") or c.args[0]
        for c in manager.query_api.query.call_args_list
    ]
    assert any('segmentId == "OLD"' in q and "count(" in q for q in queries)
    assert any('set(key: "segmentId", value: "NEW")' in q for q in queries)
    assert any('segmentId == "NEW"' in q and "count(" in q for q in queries)

    manager.delete_api.return_value.delete.assert_called_once()


def test_migration_skips_delete_when_count_mismatch():
    manager = _make_manager(counts=[100, 42])
    target = BucketTarget(manager=manager, measurement="segment_data")

    result = migrate_segment_timeseries("OLD", "NEW", [target])

    assert result.targets[0].deleted is False
    manager.delete_api.return_value.delete.assert_not_called()


def test_migration_noop_when_no_old_points():
    manager = _make_manager(counts=[0])
    target = BucketTarget(manager=manager, measurement="segment_data")

    result = migrate_segment_timeseries("OLD", "NEW", [target])

    assert result.targets[0].original_count == 0
    assert result.targets[0].deleted is False
    # Only the count(old) query should fire; no retag, no delete.
    queries = [
        c.kwargs.get("query") or c.args[0]
        for c in manager.query_api.query.call_args_list
    ]
    assert len(queries) == 1
    assert "count(" in queries[0]
    manager.delete_api.return_value.delete.assert_not_called()


def test_migration_rejects_identical_ids():
    manager = _make_manager(counts=[0])
    target = BucketTarget(manager=manager, measurement="segment_data")
    with pytest.raises(ValueError):
        migrate_segment_timeseries("SAME", "SAME", [target])


def test_migration_rejects_empty_targets():
    with pytest.raises(ValueError):
        migrate_segment_timeseries("OLD", "NEW", [])


def test_migration_handles_multiple_targets_independently():
    fcd_manager = _make_manager(counts=[50, 50])
    fcd_manager.bucket = "fcd-bucket"
    validation_manager = _make_manager(counts=[10, 5])  # mismatch → no delete
    validation_manager.bucket = "validation-bucket"

    targets = [
        BucketTarget(manager=fcd_manager, measurement="segment_data"),
        BucketTarget(manager=validation_manager, measurement="idea_validation"),
    ]

    result = migrate_segment_timeseries("OLD", "NEW", targets)

    assert result.targets[0].deleted is True
    assert result.targets[1].deleted is False
    fcd_manager.delete_api.return_value.delete.assert_called_once()
    validation_manager.delete_api.return_value.delete.assert_not_called()

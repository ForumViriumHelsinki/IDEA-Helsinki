"""Migrate InfluxDB timeseries when a segment is reissued under a new ID.

TomTom periodically reissues ``segmentId`` values for the same physical road
geometry. The segment changelog records the rename via ``geo_inherited_from``,
but the underlying timeseries points remain tagged with the old ID. This module
re-tags those points to the new ID and deletes the originals, bridging the
history gap so downstream validation queries on the new ID see full history.

Approach (Flux ``set()`` + ``to()``, then delete):

1. For each ``(bucket, measurement)`` target, run a Flux query that reads all
   points tagged ``segmentId=<old_id>`` and writes them back to the same bucket
   with ``segmentId=<new_id>``. InfluxDB's ``to()`` is idempotent by
   ``(timestamp, tag_set)`` so re-running the re-tag step is safe.
2. Verify the point counts match before deleting: if the new-ID count is less
   than the original old-ID count, abort and leave the old points in place.
3. Delete the old points via the delete API with a predicate on ``segmentId``.

Idempotency at the caller layer is provided by a ``timeseries_migrated_at``
marker in the changelog — callers check and skip migration when the marker is
set. This module is also internally safe to re-run (re-tag is no-op once data
exists at the new ID; delete is no-op once old data is gone).

Resilience: leverages the existing ``_influxdb_retry`` tenacity decorator on
``FCDInfluxDBManager`` methods for transient failures. Unrecoverable failures
are raised so the caller can skip writing the marker and retry on the next
cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from idea_shared.classes.Logger import Logger

if TYPE_CHECKING:
    from idea_shared.classes.FCDInfluxDBManager import FCDInfluxDBManager

# Re-define the same transient-exception set used by FCDInfluxDBManager so the
# migrator's retry behavior stays consistent without introducing an import
# cycle at module load time.
from http.client import IncompleteRead, RemoteDisconnected  # noqa: E402

from influxdb_client.rest import ApiException  # noqa: E402

_TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    RemoteDisconnected,
    IncompleteRead,
    OSError,
    TimeoutError,
)

_migrator_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=15),
    retry=(
        retry_if_exception_type(_TRANSIENT_EXCEPTIONS)
        & retry_if_not_exception_type(ApiException)
    ),
    reraise=True,
)

logger = Logger(__name__)


@dataclass(frozen=True)
class BucketTarget:
    """A single ``(manager, measurement)`` pair to migrate.

    The manager's configured ``bucket`` and ``org`` are used. Each target can
    point to a different manager, allowing fcd-manager to migrate both the FCD
    bucket and the validation bucket in a single call even when those buckets
    require different auth tokens.
    """

    manager: FCDInfluxDBManager
    measurement: str


@dataclass
class TargetResult:
    """Per-target migration outcome — useful for logging and tests."""

    bucket: str
    measurement: str
    original_count: int
    retagged_count: int
    deleted: bool


@dataclass
class MigrationResult:
    """Aggregate result for a full ``migrate_segment_timeseries`` call."""

    old_id: str
    new_id: str
    targets: list[TargetResult]


def _sanitize(value: str) -> str:
    """Escape a string for safe interpolation in a Flux query."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


@_migrator_retry
def _count_points(
    manager: FCDInfluxDBManager, measurement: str, segment_id: str
) -> int:
    """Count points in ``bucket`` for ``measurement`` tagged with ``segment_id``."""
    safe_measurement = _sanitize(measurement)
    safe_segment = _sanitize(segment_id)
    # Count a single field to avoid multiplying by field-count.
    # Rename ``_time`` → ``_value`` before counting so the Python client
    # does not attempt to parse the integer result as a datetime object.
    query = (
        f'from(bucket: "{manager.bucket}") '
        "|> range(start: 0) "
        f'|> filter(fn: (r) => r._measurement == "{safe_measurement}" '
        f'and r.segmentId == "{safe_segment}") '
        '|> keep(columns: ["_time", "_field"]) '
        "|> group() "
        '|> rename(columns: {"_time": "_value"}) '
        "|> count()"
    )
    tables = manager.query_api.query(query=query, org=manager.org)
    if not tables or not tables[0].records:
        return 0
    # The count is in ``_value`` after the rename + count().
    return int(tables[0].records[0].get_value() or 0)


@_migrator_retry
def _retag_points(
    manager: FCDInfluxDBManager, measurement: str, old_id: str, new_id: str
) -> None:
    """Copy points from ``old_id`` to ``new_id`` within the same bucket."""
    safe_measurement = _sanitize(measurement)
    safe_old = _sanitize(old_id)
    safe_new = _sanitize(new_id)
    # Append ``count()`` after ``to()`` so the InfluxDB server returns only
    # per-series aggregate counts rather than streaming the full written
    # dataset back to the Python client (OOM prevention for large histories).
    query = (
        f'from(bucket: "{manager.bucket}") '
        "|> range(start: 0) "
        f'|> filter(fn: (r) => r._measurement == "{safe_measurement}" '
        f'and r.segmentId == "{safe_old}") '
        f'|> set(key: "segmentId", value: "{safe_new}") '
        f'|> to(bucket: "{manager.bucket}", org: "{manager.org}") '
        "|> count()"
    )
    manager.query_api.query(query=query, org=manager.org)


@_migrator_retry
def _delete_old_points(
    manager: FCDInfluxDBManager, measurement: str, old_id: str
) -> None:
    """Delete all points in ``bucket`` for ``measurement`` tagged ``old_id``."""
    from datetime import UTC, datetime

    delete_api = manager.delete_api()
    # Delete API requires a [start, stop] range; use epoch → now to cover all.
    start = datetime(1970, 1, 1, tzinfo=UTC)
    stop = datetime.now(UTC)
    predicate = (
        f'_measurement="{_sanitize(measurement)}" AND segmentId="{_sanitize(old_id)}"'
    )
    delete_api.delete(
        start=start,
        stop=stop,
        predicate=predicate,
        bucket=manager.bucket,
        org=manager.org,
    )


def migrate_segment_timeseries(
    old_id: str,
    new_id: str,
    targets: list[BucketTarget],
) -> MigrationResult:
    """Re-tag and delete timeseries points for a renamed segment.

    For each target, re-tag points from ``old_id`` to ``new_id``, verify the
    counts match, then delete the old-ID points. Raises if re-tag fails on any
    target (delete is skipped for safety). Count mismatches abort the delete
    for that target but do not raise — the new-ID data already exists, so the
    worst case is some residual old-ID data that the next cycle can clean up.

    Args:
        old_id: The retired segment ID whose points should be rewritten.
        new_id: The new segment ID the points should be re-tagged to.
        targets: Per-bucket migration targets (manager + measurement name).

    Returns:
        Aggregate ``MigrationResult`` with per-target counts.

    Raises:
        Any exception from the underlying InfluxDB calls, surfaced through
        tenacity's retry budget. Callers should catch and log; the caller is
        responsible for leaving the idempotency marker unset so the next cycle
        retries.

    """
    if old_id == new_id:
        raise ValueError("old_id and new_id must differ")
    if not targets:
        raise ValueError("at least one BucketTarget is required")

    results: list[TargetResult] = []
    for target in targets:
        manager = target.manager
        measurement = target.measurement

        original = _count_points(manager, measurement, old_id)
        if original == 0:
            logger.info(
                f"Migration no-op for {old_id}→{new_id} on "
                f"bucket={manager.bucket} measurement={measurement} "
                "(no points tagged with old_id)."
            )
            results.append(
                TargetResult(
                    bucket=manager.bucket,
                    measurement=measurement,
                    original_count=0,
                    retagged_count=0,
                    deleted=False,
                )
            )
            continue

        _retag_points(manager, measurement, old_id, new_id)
        retagged = _count_points(manager, measurement, new_id)

        deleted = False
        if retagged >= original:
            _delete_old_points(manager, measurement, old_id)
            deleted = True
            logger.info(
                f"Migrated {original} points for {old_id}→{new_id} on "
                f"bucket={manager.bucket} measurement={measurement}; "
                "deleted original points."
            )
        else:
            logger.error(
                f"Count verification failed for {old_id}→{new_id} on "
                f"bucket={manager.bucket} measurement={measurement}: "
                f"original={original}, retagged={retagged}. "
                "Skipping delete; next cycle will retry."
            )

        results.append(
            TargetResult(
                bucket=manager.bucket,
                measurement=measurement,
                original_count=original,
                retagged_count=retagged,
                deleted=deleted,
            )
        )

    return MigrationResult(old_id=old_id, new_id=new_id, targets=results)

# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.Logger import Logger
from idea_shared.threading.file_locks import atomic_write_json, read_json_with_retry

if TYPE_CHECKING:
    from idea_shared.data.repositories import SegmentRepository

logger = Logger(__name__)


@dataclass
class ChangelogResult:
    """Result of processing segment changelog changes."""

    changelog: dict
    archive: dict
    newly_added_ids: list[str] = field(default_factory=list)
    modified_ids: list[str] = field(default_factory=list)
    removed_ids: set[str] = field(default_factory=set)


def get_fcd_geometries(fcd_file: dict) -> dict:
    """Loop through the fcd aggregation file and form a dictionary from segment IDs and their geometry.

    This dictionary is used for intersection detection with traffic disturbance data.

    Args:
        fcd_file: based on the FCD Data model (docs/data_models.md)

    Returns:
        A dictionary from segment IDs and their geometry.

    """
    if not fcd_file:
        return {}

    segment_data = fcd_file.get("segmentId")
    if not isinstance(segment_data, dict):
        logger.error("SegmentIds data is not a dictionary.")
        return {}

    fcd_segment_geometry: dict = {"segmentId": {}}

    for segment_id, segment_value in segment_data.items():
        if isinstance(segment_value, dict) and "geometry" in segment_value:
            fcd_segment_geometry["segmentId"][segment_id] = {
                "geometry": segment_value["geometry"]
            }
        else:
            logger.warning(
                f"Segment '{segment_id}' has malformed data or is missing 'geometry'. Skipping."
            )

    logger.info(
        f"FCD segment geometries retrieved for {len(fcd_segment_geometry['segmentId'])} segments."
    )
    return fcd_segment_geometry


def extract_timestamp_str_from_file_name(
    file_name: str, include_microseconds: bool | None = False
) -> str | None:
    """Function for extracting timestamps from KYMP Azure blob names: Formatted as 'YYYY-MM-DDTHH:MM:SS.ffffff.json'.

    Args:
        file_name: The blob name to parse.
        include_microseconds: If True, includes microseconds in the output.
                              If False, truncate them.

    Returns:
        A validated timestamp string or None if not found/invalid.

    """
    # Looks for a 'T' separator, then HH:MM:SS, and optionally '.' followed by 1 to 6 digits for microseconds.
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?)", file_name)

    if not match:
        logger.warning(f"No timestamp pattern found in blob name: '{file_name}'")
        return None

    datetime_str = match.group(1)
    parse_format = "%Y-%m-%dT%H:%M:%S"

    # Determine the correct format for validation based on microseconds
    if "." in datetime_str:
        parse_format += ".%f"

    try:
        dt_obj = datetime.strptime(datetime_str, parse_format)
        if include_microseconds:
            return dt_obj.strftime("%Y-%m-%dT%H:%M:%S.%f")
        else:
            return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")

    except ValueError:
        logger.warning(
            f"Could not parse valid datetime from extracted string '{datetime_str}' in '{file_name}'"
        )
        return None


def parse_json_from_bytes(
    content_bytes: bytes, file_name_for_log: str | None = "json file"
) -> dict | None:
    """Function for parsing JSON data from bytes.

    Args:
        content_bytes: The bytes to parse.
        file_name_for_log: The name logging.

    Returns:
        The parsed JSON data or None is the data could not be parsed.

    """
    try:
        content_str = content_bytes.decode("utf-8")
        return json.loads(content_str)
    except UnicodeDecodeError as ude:
        logger.error(
            f"Failed to decode content of '{file_name_for_log}' as UTF-8: {ude}"
        )
        return None
    except json.JSONDecodeError as jde:
        logger.error(f"Failed to parse JSON from blob '{file_name_for_log}': {jde}")
        return None
    except Exception as e:
        logger.error(
            f"Unexpected error parsing JSON from blob '{file_name_for_log}': {e}"
        )
        return None


def write_json_records(records: dict, json_file: str) -> bool:
    """Function for writing JSON records to a file using atomic writes.

    Uses atomic write pattern (temp file + rename) to prevent corruption
    and includes retry logic for ESTALE errors on GCS FUSE mounts.

    Args:
        records: The records to write.
        json_file: The name of the JSON file to write.

    Returns:
        True if the file was written, False otherwise.

    """
    segment_ids = records.get("segmentId")
    if not isinstance(segment_ids, dict):
        logger.error("JSON record did not contain a Dictionary for different segments")
        return False
    json_file_path = Path(json_file)

    try:
        atomic_write_json(json_file_path, records)
        logger.info(
            f"Successfully wrote {len(segment_ids)} records to '{json_file_path}'."
        )
        return True
    except OSError as ioe:
        logger.error(f"Failed to write JSON records to '{json_file}': {ioe}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error writing JSON records to '{json_file}': {e}")
        return False


def read_existing_json_records(json_file: str) -> dict:
    """Function for reading existing JSON records from a file.

    Args:
        json_file: The name of the JSON file to read.

    Returns:
        A dictionary from the JSON file.

    """
    records = {}
    existing_content = read_json_with_retry(json_file)
    if existing_content is None:
        return records
    if isinstance(existing_content, dict):
        segment_ids = existing_content.get("segmentId")
        if isinstance(segment_ids, dict):
            records = existing_content
            logger.info(
                f"Read {len(segment_ids)} existing segment records from '{json_file}'."
            )
        else:
            logger.warning(
                f"Existing JSON file '{json_file}' did not contain a Dictionary for different segments. It will be overwritten."
            )
    else:
        logger.warning(
            f"Existing JSON file '{json_file}' did not contain a Dictionary. It will be overwritten."
        )
    return records


def find_matching_historical_segments(
    new_segment_geometries: dict,
    removed_segment_records: dict,
    match_threshold: float = 0.7,
    buffer_distance_meters: float = 5.0,
    metric_crs: str = "EPSG:3879",
    geographic_crs: str = "EPSG:4326",
) -> dict:
    """Finds removed segments that geographically match new segments for history inheritance.

    When FCD segments are updated by TomTom, old segment IDs may be replaced by new ones at
    the same physical location. This function detects such replacements by comparing segment
    geometries spatially, enabling new segments to inherit the history of the segments they
    replaced.

    The matching score is computed as:
        min(fraction of new segment within old segment's buffer,
            fraction of old segment within new segment's buffer)
    Both segments must have significant overlap for a match to be recorded.

    Args:
        new_segment_geometries: Dict of {segment_id: geometry_dict} for newly added segments.
        removed_segment_records: Dict of {segment_id: record} for recently removed segments
            as they appear in the master changelog before archiving.
        match_threshold: Minimum overlap score (0.0–1.0) to consider two segments matching.
            Defaults to 0.7 (70 % overlap required on both sides).
        buffer_distance_meters: Distance in meters used to buffer segments when computing
            overlap. Defaults to 5.0 m (narrow enough to avoid cross-lane matching on
            bidirectional roads where lane separation is typically 7–10 m).
        metric_crs: CRS string for metric (buffering) operations. Defaults to "EPSG:3879".
        geographic_crs: CRS string of the input geometries. Defaults to "EPSG:4326".

    Returns:
        Dict mapping {new_segment_id: best_matching_old_segment_id} for every match that
        exceeds the threshold. Each new segment is matched to at most one old segment
        (the best-scoring one).

    """
    if not new_segment_geometries or not removed_segment_records:
        return {}

    transformer = Transformer.from_crs(geographic_crs, metric_crs, always_xy=True)

    def project(geom_dict):
        return shapely_transform(transformer.transform, shape(geom_dict))

    # Pre-project and buffer all removed segments once.
    projected_old: dict = {}
    buffered_old: dict = {}
    for old_id, old_record in removed_segment_records.items():
        old_geom_dict = old_record.get("current_geometry")
        if not old_geom_dict:
            continue
        try:
            old_geom = project(old_geom_dict)
            projected_old[old_id] = old_geom
            buffered_old[old_id] = old_geom.buffer(
                buffer_distance_meters, cap_style="flat"
            )
        except Exception as e:
            logger.warning(
                f"Could not project removed segment '{old_id}' for geo-matching: {e}"
            )

    if not projected_old:
        return {}

    matches: dict = {}

    for new_id, new_geom_dict in new_segment_geometries.items():
        try:
            new_geom = project(new_geom_dict)
            if new_geom.length == 0:
                continue
            new_buffer = new_geom.buffer(buffer_distance_meters, cap_style="flat")
        except Exception as e:
            logger.warning(
                f"Could not project new segment '{new_id}' for geo-matching: {e}"
            )
            continue

        best_score = 0.0
        best_old_id = None

        for old_id, old_geom in projected_old.items():
            if old_geom.length == 0:
                continue
            try:
                # Fraction of the new segment covered by the old segment's buffer.
                new_overlap = (
                    new_geom.intersection(buffered_old[old_id]).length / new_geom.length
                )
                # Fraction of the old segment covered by the new segment's buffer.
                old_overlap = old_geom.intersection(new_buffer).length / old_geom.length
                # Both sides must overlap substantially.
                score = min(new_overlap, old_overlap)
                if score > best_score:
                    best_score = score
                    best_old_id = old_id
            except Exception as e:
                logger.warning(
                    f"Error comparing new segment '{new_id}' with old '{old_id}': {e}"
                )

        if best_score >= match_threshold and best_old_id is not None:
            matches[new_id] = best_old_id
            logger.info(
                f"New segment '{new_id}' geographically matches removed segment "
                f"'{best_old_id}' (overlap score: {best_score:.2f})."
            )

    return matches


def _collect_lookback_candidates(
    archived_segments: dict,
    changelog: dict,
    processing_date: datetime,
    lookback_hours: float,
    same_cycle_ids: set[str],
) -> dict[str, dict]:
    """Collect archived segments eligible for cross-cycle geo-inheritance.

    Returns archived records whose ``date_archived`` falls within the
    ``lookback_hours`` window ending at ``processing_date``, excluding:

    - segments already collected as same-cycle candidates, and
    - segments already referenced as ``geo_inherited_from`` on any existing
      changelog entry (guards against double-inheritance across cycles).

    Records with a missing or unparseable ``date_archived`` are skipped.

    Args:
        archived_segments: ``{old_id: record}`` archive dict.
        changelog: Current changelog, scanned for existing
            ``geo_inherited_from`` references.
        processing_date: Timestamp for the current processing cycle.
        lookback_hours: Size of the lookback window.
        same_cycle_ids: Segment IDs already included in the same-cycle
            candidate pool — excluded to avoid duplicate entries.

    Returns:
        ``{old_id: record}`` of lookback candidates.

    """
    already_inherited: set[str] = {
        record["geo_inherited_from"]
        for record in changelog.values()
        if isinstance(record, dict) and "geo_inherited_from" in record
    }
    # Normalize processing_date to UTC-aware so comparisons against archived
    # timestamps are unambiguous regardless of whether callers pass naive or
    # aware values. Naive inputs are assumed to represent UTC, matching the
    # convention used elsewhere in this module (see _run_pending_migrations).
    processing_date_utc = (
        processing_date
        if processing_date.tzinfo is not None
        else processing_date.replace(tzinfo=UTC)
    )
    cutoff = processing_date_utc - timedelta(hours=lookback_hours)

    candidates: dict[str, dict] = {}
    for old_id, record in archived_segments.items():
        if old_id in same_cycle_ids or old_id in already_inherited:
            continue
        date_archived_str = record.get("date_archived")
        if not date_archived_str:
            continue
        try:
            date_archived = datetime.fromisoformat(date_archived_str)
        except ValueError:
            continue
        # Normalize archived timestamp to UTC-aware for comparison with the
        # (already UTC-aware) cutoff. Assumes naive archived timestamps are UTC.
        if date_archived.tzinfo is None:
            date_archived = date_archived.replace(tzinfo=UTC)
        if date_archived < cutoff:
            continue
        # Strictly cross-cycle: exclude anything archived at the exact same
        # instant as the current processing_date (that's a same-cycle event).
        candidates[old_id] = record
    return candidates


def _run_pending_migrations(
    changelog: dict,
    processing_date: datetime,
    migration_targets: list,
) -> None:
    """Run or retry InfluxDB timeseries migration for all unmigrated geo-inherited segments.

    Scans *changelog* for entries that carry ``geo_inherited_from`` but lack
    ``timeseries_migrated_at`` and attempts to migrate each one.  Decoupling
    migration execution from the initial detection cycle means that transient
    InfluxDB failures on the first attempt are automatically retried on
    subsequent FCD cycles rather than silently dropped.

    Args:
        changelog: The current segment changelog dict.  Mutated in place by
            adding ``timeseries_migrated_at`` markers on successful migrations.
        processing_date: Used to derive the timezone for the migration
            timestamp; falls back to UTC when ``tzinfo`` is not set.
        migration_targets: List of ``BucketTarget`` instances passed to the
            migrator.

    """
    # Local import keeps the InfluxDB dependency optional for callers that
    # don't provide migration_targets (e.g. unit tests that omit the param).
    from idea_shared.classes.InfluxDBSegmentMigrator import migrate_segment_timeseries

    for seg_id, record in changelog.items():
        if "geo_inherited_from" not in record or "timeseries_migrated_at" in record:
            continue
        old_id = record["geo_inherited_from"]
        try:
            migrate_segment_timeseries(
                old_id=old_id,
                new_id=seg_id,
                targets=migration_targets,
            )
            changelog[seg_id]["timeseries_migrated_at"] = datetime.now(
                processing_date.tzinfo or UTC
            ).isoformat()
            logger.info(f"Timeseries migration complete for '{old_id}' → '{seg_id}'.")
        except Exception as exc:
            logger.error(
                f"Timeseries migration failed for '{old_id}' → '{seg_id}': {exc}. "
                "Changelog will still record geo_inherited_from and the next "
                "cycle will retry the migration."
            )


def update_segment_changelog(
    fresh_mapping_file_path: str,
    changelog_file_path: str,
    archive_file_path: str,
    processing_date: datetime,
    migration_targets: list | None = None,
    lookback_hours: float | None = None,
) -> None:
    """Compare a fresh segment mapping file against a master changelog to detect, log, and catalog segment changes.

    Moves removed segments to an archive. Assumes the fresh mapping file represents the current and valid geometry structure for segments.

    Args:
        fresh_mapping_file_path: Path to the new segments_mapping.json.
        changelog_file_path: Path to the persistent JSON changelog file.
        archive_file_path: Path to the JSON archive for removed segments.
        processing_date: Date the segment changelog was processed (datetime.now(timezone.utc)) or if processing historical data, the past date for processing.
        migration_targets: Optional list of ``BucketTarget`` instances for the
            InfluxDB segment migration. When a geo-inheritance event is
            detected (a new segment ID replaces a retired one at the same
            location), the migrator re-tags the retired segment's timeseries
            points to the new ID and records a ``timeseries_migrated_at``
            marker in the changelog. If ``None``, migration is skipped.
        lookback_hours: Optional window (hours) for cross-cycle geo-inheritance.
            When set, archived segments with ``date_archived`` within this
            window are considered as candidates in addition to same-cycle
            removals. Archived records are left in place on match; a guard
            against double-inheritance excludes any ``old_id`` that already
            appears as ``geo_inherited_from`` on an existing changelog entry.
            ``None`` (default) preserves the original same-cycle-only behaviour.

    """
    # Prepare the Path variables
    changelog_path = Path(changelog_file_path)
    archive_path = Path(archive_file_path)
    mapping_file_path = Path(fresh_mapping_file_path)

    # Check if the change log (master segment history file) is already available.
    changelog = {}
    if changelog_path.exists():
        try:
            with open(changelog_path, encoding="utf-8") as f:
                changelog = json.load(f)
        except json.JSONDecodeError as e:
            # Recovery: backup corrupted file and start fresh instead of aborting
            # This handles cases where pod termination leaves truncated JSON
            logger.warning(f"Changelog file corrupted: {e}. Attempting recovery...")

            backup_suffix = processing_date.strftime("%Y%m%d_%H%M%S")
            backup_path = changelog_path.with_suffix(f".{backup_suffix}.corrupted")
            try:
                shutil.copy2(changelog_path, backup_path)
                logger.info(f"Corrupted file backed up to: {backup_path}")
            except OSError as backup_error:
                logger.warning(f"Could not backup corrupted file: {backup_error}")

            # Start fresh - will rebuild from current mapping
            changelog = {}
            logger.warning(
                "Starting with empty changelog. Historical geometry changes will be lost."
            )
        except OSError as e:
            logger.error(
                f"Could not load changelog file '{changelog_path}'. Aborting. Error: {e}"
            )
            return

    # Check if the archived segment file (archived segment history file) is already available.
    archived_segments = {}
    if archive_path.exists():
        try:
            with open(archive_path, encoding="utf-8") as f:
                archived_segments = json.load(f)
        except (OSError, json.JSONDecodeError):
            logger.warning(
                f"Could not load archive file '{archive_path}'. A new one may be created."
            )

    # Load the fresh segment mapping, end function if none is available.
    fresh_segments = {}
    try:
        with open(mapping_file_path, encoding="utf-8") as f:
            fresh_data = json.load(f)
        for seg_id, seg_value in fresh_data.get("segmentId", {}).items():
            if isinstance(seg_value, dict) and "geometry" in seg_value:
                fresh_segments[seg_id] = seg_value["geometry"]
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not read or parse fresh segment mapping file: {e}")
        return

    # Get the segment ID from both files (Master - Fresh)
    master_ids = set(changelog.keys())
    fresh_ids = set(fresh_segments.keys())

    # Check is segments are missing (removed) from the fresh mapping file.
    removed_segments_ids = master_ids - fresh_ids
    if removed_segments_ids:
        logger.warning(
            f"DETECTED {len(removed_segments_ids)} REMOVED SEGMENTS: {list(removed_segments_ids)}"
        )
        for seg_id in removed_segments_ids:
            removed_record = changelog.pop(seg_id)
            removed_record["date_archived"] = processing_date.isoformat()
            archived_segments[seg_id] = removed_record

    # Check for new segments and segments that have been modified.
    newly_added_ids = []
    modified_ids = []
    for seg_id, geometry in fresh_segments.items():
        geom_str = json.dumps(geometry, sort_keys=True)
        # SHA-256 is used to determine changes in the segments catalogued state.
        geom_hash = hashlib.sha256(geom_str.encode("utf-8")).hexdigest()

        if seg_id not in changelog:
            # This is a new segment
            newly_added_ids.append(seg_id)
            changelog[seg_id] = {
                "current_geometry": geometry,
                "current_hash": geom_hash,
                "date_added": processing_date.isoformat(),
                "history": [],
            }
        elif changelog[seg_id]["current_hash"] != geom_hash:
            # This segment's geometry has been modified
            modified_ids.append(seg_id)

            # Archive the old state to its history
            archive_entry = {
                "date_archived": processing_date.isoformat(),
                "geometry": changelog[seg_id]["current_geometry"],
            }
            changelog[seg_id]["history"].append(archive_entry)

            # Update the changelog to the new state
            changelog[seg_id]["current_geometry"] = geometry
            changelog[seg_id]["current_hash"] = geom_hash

    # Report changes found
    if newly_added_ids:
        logger.info(f"DETECTED {len(newly_added_ids)} NEW SEGMENTS: {newly_added_ids}")
    if modified_ids:
        logger.info(
            f"DETECTED {len(modified_ids)} MODIFIED SEGMENT GEOMETRIES: {modified_ids}"
        )
    if not newly_added_ids and not removed_segments_ids and not modified_ids:
        logger.info("Segment inventory check complete. No changes detected.")

    # Geo-inheritance: check whether any new segment geographically matches a
    # removed one. Same-cycle removals are always eligible; when
    # ``lookback_hours`` is set, recently archived segments (from previous
    # cycles) are added as additional candidates to bridge cross-cycle
    # replacements. If a match is found, the new segment inherits the removed
    # segment's accumulated history so that the InfluxDB history gap caused by
    # a segment ID change can be bridged.
    if newly_added_ids and (removed_segments_ids or lookback_hours is not None):
        removed_records_for_matching = {
            seg_id: archived_segments[seg_id]
            for seg_id in removed_segments_ids
            if seg_id in archived_segments
        }
        if lookback_hours is not None:
            lookback_candidates = _collect_lookback_candidates(
                archived_segments=archived_segments,
                changelog=changelog,
                processing_date=processing_date,
                lookback_hours=lookback_hours,
                same_cycle_ids=set(removed_records_for_matching.keys()),
            )
            removed_records_for_matching.update(lookback_candidates)
            if lookback_candidates:
                logger.info(
                    f"Considering {len(lookback_candidates)} cross-cycle "
                    f"archived segment(s) within {lookback_hours}h lookback "
                    "for geo-inheritance."
                )
        new_geometries_for_matching = {
            seg_id: fresh_segments[seg_id] for seg_id in newly_added_ids
        }
        geo_matches = find_matching_historical_segments(
            new_geometries_for_matching, removed_records_for_matching
        )

        for new_id, old_id in geo_matches.items():
            old_record = archived_segments[old_id]
            # Build the inherited history: everything the old segment accumulated,
            # plus its final (current) geometry as the most recent archived entry.
            inherited_history = old_record.get("history", []).copy()
            inherited_history.append(
                {
                    "date_archived": old_record.get(
                        "date_archived", processing_date.isoformat()
                    ),
                    "geometry": old_record["current_geometry"],
                }
            )
            # Prepend inherited entries so they appear before any changes on the new segment.
            changelog[new_id]["history"] = (
                inherited_history + changelog[new_id]["history"]
            )
            changelog[new_id]["geo_inherited_from"] = old_id
            logger.info(
                f"Segment '{new_id}' inherited {len(inherited_history)} history "
                f"entries from removed segment '{old_id}'."
            )

        if geo_matches:
            logger.info(
                f"Geo-inheritance complete: {len(geo_matches)} new segment(s) "
                f"inherited history from removed segment(s)."
            )

    # Run or retry pending InfluxDB timeseries migrations.
    # Decoupled from the detection block above so that any segment in the
    # changelog with ``geo_inherited_from`` but without
    # ``timeseries_migrated_at`` is retried on every cycle until it succeeds.
    if migration_targets:
        _run_pending_migrations(changelog, processing_date, migration_targets)

    # Update files using atomic writes to prevent corruption from ESTALE errors
    try:
        atomic_write_json(changelog_path, changelog)
        logger.info("Segment changelog file has been updated.")

        if removed_segments_ids:
            atomic_write_json(archive_path, archived_segments)
            logger.info("Segment archive file has been updated.")
    except OSError as e:
        logger.error(f"Failed to write updated changelog or archive file: {e}")


def extract_fresh_segments(segments_data: dict) -> dict:
    """Extract segment_id -> geometry mapping from segments data.

    Args:
        segments_data: Dict in format ``{"segmentId": {id: {"geometry": ...}}}``

    Returns:
        Dict mapping segment_id to geometry dict.

    """
    fresh_segments = {}
    for seg_id, seg_value in segments_data.get("segmentId", {}).items():
        if isinstance(seg_value, dict) and "geometry" in seg_value:
            fresh_segments[seg_id] = seg_value["geometry"]
    return fresh_segments


def process_segment_changelog(
    fresh_segments: dict,
    changelog: dict,
    archive: dict,
    processing_date: datetime,
) -> ChangelogResult:
    """Pure logic for comparing segments against changelog and detecting changes.

    This function contains the core changelog processing logic without any file I/O,
    making it testable and reusable across different storage backends.

    Args:
        fresh_segments: Dict mapping segment_id to geometry dict.
        changelog: Existing changelog dict (segment_id -> history record).
        archive: Existing archive dict (segment_id -> archived record).
        processing_date: Timestamp for recording changes.

    Returns:
        ChangelogResult with updated changelog, archive, and change details.

    """
    # Deep copy to avoid mutating caller's data (nested dicts contain lists/dicts)
    changelog = copy.deepcopy(changelog)
    archive = copy.deepcopy(archive)

    master_ids = set(changelog.keys())
    fresh_ids = set(fresh_segments.keys())

    # Detect removed segments
    removed_ids = master_ids - fresh_ids
    if removed_ids:
        logger.warning(
            f"DETECTED {len(removed_ids)} REMOVED SEGMENTS: {list(removed_ids)}"
        )
        for seg_id in removed_ids:
            removed_record = changelog.pop(seg_id)
            removed_record["date_archived"] = processing_date.isoformat()
            archive[seg_id] = removed_record

    # Detect new and modified segments
    newly_added_ids = []
    modified_ids = []
    for seg_id, geometry in fresh_segments.items():
        geom_str = json.dumps(geometry, sort_keys=True)
        geom_hash = hashlib.sha256(geom_str.encode("utf-8")).hexdigest()

        if seg_id not in changelog:
            newly_added_ids.append(seg_id)
            changelog[seg_id] = {
                "current_geometry": geometry,
                "current_hash": geom_hash,
                "date_added": processing_date.isoformat(),
                "history": [],
            }
        elif changelog[seg_id]["current_hash"] != geom_hash:
            modified_ids.append(seg_id)
            archive_entry = {
                "date_archived": processing_date.isoformat(),
                "geometry": changelog[seg_id]["current_geometry"],
            }
            changelog[seg_id]["history"].append(archive_entry)
            changelog[seg_id]["current_geometry"] = geometry
            changelog[seg_id]["current_hash"] = geom_hash

    # Report changes
    if newly_added_ids:
        logger.info(f"DETECTED {len(newly_added_ids)} NEW SEGMENTS: {newly_added_ids}")
    if modified_ids:
        logger.info(
            f"DETECTED {len(modified_ids)} MODIFIED SEGMENT GEOMETRIES: {modified_ids}"
        )
    if not newly_added_ids and not removed_ids and not modified_ids:
        logger.info("Segment inventory check complete. No changes detected.")

    return ChangelogResult(
        changelog=changelog,
        archive=archive,
        newly_added_ids=newly_added_ids,
        modified_ids=modified_ids,
        removed_ids=removed_ids,
    )


def update_segment_changelog_from_repo(
    repository: SegmentRepository,
    processing_date: datetime,
    migration_targets: list | None = None,
    lookback_hours: float | None = None,
) -> None:
    """Update segment changelog using a SegmentRepository.

    Repository-based equivalent of update_segment_changelog(). Reads segments,
    changelog, and archive from the repository, processes changes, and writes
    results back.  Includes geo-inheritance detection and optional InfluxDB
    timeseries migration (same semantics as ``update_segment_changelog``).

    Args:
        repository: SegmentRepository instance providing data access.
        processing_date: Timestamp for recording changes.
        migration_targets: Optional list of ``BucketTarget`` instances for the
            InfluxDB segment migration.  When a geo-inheritance event is
            detected, the migrator re-tags retired segment timeseries to the
            new ID and records a ``timeseries_migrated_at`` marker.  Pending
            migrations are also retried on every call until they succeed.  If
            ``None``, migration is skipped.
        lookback_hours: Optional window (hours) for cross-cycle geo-inheritance.
            When set, archived segments with ``date_archived`` within this
            window are considered as candidates in addition to same-cycle
            removals. A guard against double-inheritance excludes any
            ``old_id`` already referenced as ``geo_inherited_from`` in the
            changelog. ``None`` (default) preserves same-cycle-only behaviour.

    """
    segments_data = repository.get_segments()
    if not segments_data:
        logger.warning("Could not read segment mapping from repository.")
        return

    fresh_segments = extract_fresh_segments(segments_data)
    if not fresh_segments:
        logger.error("No valid segments found in mapping data.")
        return

    changelog = repository.get_changelog()
    archive = repository.get_archive()

    result = process_segment_changelog(
        fresh_segments, changelog, archive, processing_date
    )

    # Geo-inheritance: check whether any new segment geographically matches a
    # removed one and inherit its history (mirrors update_segment_changelog).
    if result.newly_added_ids and (result.removed_ids or lookback_hours is not None):
        removed_records_for_matching = {
            seg_id: result.archive[seg_id]
            for seg_id in result.removed_ids
            if seg_id in result.archive
        }
        if lookback_hours is not None:
            lookback_candidates = _collect_lookback_candidates(
                archived_segments=result.archive,
                changelog=result.changelog,
                processing_date=processing_date,
                lookback_hours=lookback_hours,
                same_cycle_ids=set(removed_records_for_matching.keys()),
            )
            removed_records_for_matching.update(lookback_candidates)
            if lookback_candidates:
                logger.info(
                    f"Considering {len(lookback_candidates)} cross-cycle "
                    f"archived segment(s) within {lookback_hours}h lookback "
                    "for geo-inheritance."
                )
        new_geometries_for_matching = {
            seg_id: fresh_segments[seg_id] for seg_id in result.newly_added_ids
        }
        geo_matches = find_matching_historical_segments(
            new_geometries_for_matching, removed_records_for_matching
        )
        for new_id, old_id in geo_matches.items():
            old_record = result.archive[old_id]
            inherited_history = old_record.get("history", []).copy()
            inherited_history.append(
                {
                    "date_archived": old_record.get(
                        "date_archived", processing_date.isoformat()
                    ),
                    "geometry": old_record["current_geometry"],
                }
            )
            result.changelog[new_id]["history"] = (
                inherited_history + result.changelog[new_id]["history"]
            )
            result.changelog[new_id]["geo_inherited_from"] = old_id
            logger.info(
                f"Segment '{new_id}' inherited {len(inherited_history)} history "
                f"entries from removed segment '{old_id}'."
            )
        if geo_matches:
            logger.info(
                f"Geo-inheritance complete: {len(geo_matches)} new segment(s) "
                f"inherited history from removed segment(s)."
            )

    # Run or retry pending InfluxDB timeseries migrations.
    if migration_targets:
        _run_pending_migrations(result.changelog, processing_date, migration_targets)

    try:
        repository.save_changelog(result.changelog)
        if result.removed_ids:
            repository.save_archive(result.archive)
    except OSError as e:
        logger.error(f"Failed to write updated changelog or archive: {e}")

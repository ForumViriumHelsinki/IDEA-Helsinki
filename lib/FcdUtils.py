#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import re
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from classes.Logger import Logger

logger = Logger(__name__)

def get_fcd_geometries(fcd_file: dict) -> dict:
    """
    Loops through the fcd aggregation file and forms a dictionary from segment IDs and their geometry.
    This dictionary is used for intersection detection with traffic disturbance data.
    Args:
        fcd_file: based on the FCD Data model (docs/data_models.md)
    Returns:
        A dictionary from segment IDs and their geometry.
    """
    if not fcd_file:
        return {}

    segment_data = fcd_file.get("segmentId", {})
    if not isinstance(segment_data, dict):
        logger.error("SegmentIds data is not a dictionary.")
        return {}

    fcd_segment_geometry: dict = {"segmentId": {}}

    for segment_id, segment_value in segment_data.items():
        if isinstance(segment_value, dict) and "geometry" in segment_value:
            fcd_segment_geometry["segmentId"][segment_id] = {"geometry": segment_value["geometry"]}
        else:
            logger.warning(f"Segment '{segment_id}' has malformed data or is missing 'geometry'. Skipping.")

    logger.info(f"FCD segment geometries retrieved for {len(fcd_segment_geometry['segmentId'])} segments.")
    return fcd_segment_geometry

def extract_timestamp_str_from_file_name(file_name: str, include_microseconds: bool | None = False) -> str | None:
    """
    Function for extracting timestamps from KYMP Azure blob names: Formatted as 'YYYY-MM-DDTHH:MM:SS.ffffff.json'

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
        logger.warning(f"Could not parse valid datetime from extracted string '{datetime_str}' in '{file_name}'")
        return None

def parse_json_from_bytes(content_bytes: bytes, file_name_for_log: str | None = "json file") -> dict | None:
    """
    Function for parsing JSON data from bytes.

    Args:
        content_bytes: The bytes to parse.
        file_name_for_log: The name logging.

    returns:
        The parsed JSON data or None is the data could not be parsed.
    """
    try:
        content_str = content_bytes.decode('utf-8')
        return json.loads(content_str)
    except UnicodeDecodeError as ude:
        logger.error(f"Failed to decode content of '{file_name_for_log}' as UTF-8: {ude}")
        return None
    except json.JSONDecodeError as jde:
        logger.error(f"Failed to parse JSON from blob '{file_name_for_log}': {jde}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing JSON from blob '{file_name_for_log}': {e}")
        return None

def write_json_records(records: dict, json_file:str) -> bool:
    """
    Function for writing JSON records to a file.
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
        json_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4)
        logger.info(f"Successfully wrote {len(segment_ids)} records to '{json_file_path}'.")
        return True
    except IOError as ioe:
        logger.error(f"Failed to write JSON records to '{json_file}': {ioe}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error writing JSON records to '{json_file}': {e}")
        return False

def read_existing_json_records(json_file: str) -> dict:
    """
    Function for reading existing JSON records from a file.
    Args:
        json_file: The name of the JSON file to read.

    Returns:
        A dictionary from the JSON file.
    """
    records = {}
    json_file_path = Path(json_file)
    if json_file_path.exists() and json_file_path.stat().st_size > 0:
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                existing_content = json.load(f)
            if isinstance(existing_content, dict):
                segment_ids = existing_content.get("segmentId", {})
                if isinstance(segment_ids, dict):
                    records = existing_content
                    logger.info(f"Read {len(segment_ids)} existing segment records from '{json_file_path}'.")
                else:
                   logger.warning(f"Existing JSON file '{json_file_path}' did not contain a Dictionary for different segments. It will be overwritten.")
            else:
                logger.warning(f"Existing JSON file '{json_file_path}' did not contain a Dictionary. It will be overwritten.")
        except json.JSONDecodeError:
            logger.warning(f"Could not decode existing JSON from '{json_file}'. It will be overwritten.")
        except Exception as e:
            logger.error(f"Error reading or parsing existing JSON file '{json_file}': {e}. It will be overwritten.")
    return records

def update_segment_changelog(fresh_mapping_file_path: str,changelog_file_path: str,archive_file_path: str) -> None:
    """
    Compares a fresh segment mapping file against a master changelog to detect,
    log, and catalog segment changes, moving removed segments to an archive.
    Note that the assumption is that the fresh mapping file represents the current and valid geometry structure for segments.

    Args:
        fresh_mapping_file_path: Path to the new segments_mapping.json.
        changelog_file_path: Path to the persistent JSON changelog file.
        archive_file_path: Path to the JSON archive for removed segments.
    """
    # Prepare the Path variables
    changelog_path = Path(changelog_file_path)
    archive_path = Path(archive_file_path)
    mapping_file_path = Path(fresh_mapping_file_path)

    # Check if the change log (master segment history file) is already available.
    changelog = {}
    if changelog_path.exists():
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Could not load changelog file '{changelog_path}'. Aborting. Error: {e}")
            return

    # Check if the archived segment file (archived segment history file) is already available.
    archived_segments = {}
    if archive_path.exists():
        try:
            with open(archive_path, 'r', encoding='utf-8') as f:
                archived_segments = json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning(f"Could not load archive file '{archive_path}'. A new one may be created.")

    # Load the fresh segment mapping, end function if none is available.
    fresh_segments = {}
    try:
        with open(mapping_file_path, 'r', encoding='utf-8') as f:
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
        logger.warning(f"DETECTED {len(removed_segments_ids)} REMOVED SEGMENTS: {list(removed_segments_ids)}")
        for seg_id in removed_segments_ids:
            removed_record = changelog.pop(seg_id)
            removed_record['archived_at'] = datetime.now(timezone.utc).isoformat()
            archived_segments[seg_id] = removed_record

    # Check for new segments and segments that have been modified.
    newly_added_ids = []
    modified_ids = []
    for seg_id, geometry in fresh_segments.items():
        geom_str = json.dumps(geometry, sort_keys=True)
        #SHA-256 is used to determine changes in the segments catalogued state.
        geom_hash = hashlib.sha256(geom_str.encode('utf-8')).hexdigest()

        if seg_id not in changelog:
            # This is a new segment
            newly_added_ids.append(seg_id)
            changelog[seg_id] = {
                "current_geometry": geometry,
                "current_hash": geom_hash,
                "history": []
            }
        elif changelog[seg_id]["current_hash"] != geom_hash:
            # This segment's geometry has been modified
            modified_ids.append(seg_id)

            # Archive the old state to its history
            archive_entry = {
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "geometry": changelog[seg_id]["current_geometry"]
            }
            changelog[seg_id]["history"].append(archive_entry)

            # Update the changelog to the new state
            changelog[seg_id]["current_geometry"] = geometry
            changelog[seg_id]["current_hash"] = geom_hash

    # Report changes found
    if newly_added_ids:
        logger.info(f"DETECTED {len(newly_added_ids)} NEW SEGMENTS: {newly_added_ids}")
    if modified_ids:
        logger.info(f"DETECTED {len(modified_ids)} MODIFIED SEGMENT GEOMETRIES: {modified_ids}")
    if not newly_added_ids and not removed_segments_ids and not modified_ids:
        logger.info("Segment inventory check complete. No changes detected.")

    # Update files
    try:
        with open(changelog_path, 'w', encoding='utf-8') as f:
            json.dump(changelog, f, indent=4)
        logger.info("Segment changelog file has been updated.")

        if removed_segments_ids:
            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archived_segments, f, indent=4)
            logger.info("Segment archive file has been updated.")
    except IOError as e:
        logger.error(f"Failed to write updated changelog or archive file: {e}")
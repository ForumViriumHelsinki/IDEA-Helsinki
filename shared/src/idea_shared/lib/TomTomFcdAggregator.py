# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
from datetime import datetime

from idea_shared.classes.Logger import Logger

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
logger = Logger(__name__)


def convert_confidence_to_fcd_num(confidence: int):
    """Converts a confidence_level (0-100) to fcd value (0-10) used in the IDEA algorithm.
    - confidence_level <= 70 maps to fcd = 0
    - confidence_level == 100 maps to fcd = 10
    - Values between 70 and 100 are linearly scaled.

    NOTE: This is just the first "quick-and-dirty" estimation method.

    Args:
        confidence from a time series segment, value range 0-100.

    Returns:
        Converted estimate of numerical FCD value, None if confidence is None (IDEA accepts Null values)

    """
    if confidence is None:
        return None
    if confidence <= 70:
        return 0
    else:
        scaled_value = ((confidence - 70) / (100 - 70)) * 10
        return min(10, round(scaled_value))


# Legacy function for FCD data model file validation.
def validate_tomtom_aggregation_file(data: dict) -> dict:
    """Function validates that the TomTom aggregation file is valid and can be used for updating.

    Args: data
        Uploaded TomTom aggregation file that contains aggregated TomTom data.

    Returns:
        A validated dictionary or an empty dictionary.

    """
    segment_ids = data.get("segmentId")
    if not isinstance(segment_ids, dict):
        logger.warning(
            "Dictionary has no segmentId key has no dictionary associated to it, returning an empty dictionary!"
        )
        return {}

    for key, value in segment_ids.items():
        if not key.isdigit():
            logger.warning(
                "Dictionary key is not an Integer (segment ID), returning an empty dictionary!"
            )
            return {}
        if not isinstance(value, dict):
            logger.warning(
                "Dictionary key has no dictionary associated to it, returning an empty dictionary!"
            )
            return {}

        if "geometry" not in value or "detailedSegment" not in value:
            logger.warning(
                "Dictionaries geometry and detailedSegment keys missing, returning an empty dictionary!"
            )
            return {}

        geometry = value.get("geometry")
        if not isinstance(geometry, dict):
            logger.warning(
                "Dictionaries geometry key has no dictionary associated to it, returning an empty dictionary!"
            )
            return {}
        if geometry.get("type") != "LineString":
            logger.warning(
                "Dictionaries geometry is not 'LineString' format, returning an empty dictionary!"
            )
            return {}
        coordinates = geometry.get("coordinates")
        if not (
            isinstance(coordinates, list)
            and all(
                isinstance(coord, list)
                and len(coord) == 2
                and isinstance(coord[0], float)
                and isinstance(coord[1], float)
                for coord in coordinates
            )
        ):
            logger.warning(
                "Dictionaries geometry coordinates are malformed, returning an empty dictionary!"
            )
            return {}

        detailed_segment = value.get("detailedSegment")
        if not isinstance(detailed_segment, dict) or not detailed_segment:
            logger.warning(
                "Dictionaries 'detailedSegment' is not a dictionary, returning an empty dictionary!"
            )
            return {}

        dates = detailed_segment.get("date")
        if not isinstance(dates, dict):
            logger.warning(
                "Dictionaries 'detailedSegment' date is not a Dictionary, returning an empty dictionary!"
            )
            return {}

    logger.info("TomTom aggregation file validated correctly")
    return data


def transform_single_tomtom_json_data_for_aggregation(
    raw_data_from_tomtom_json: dict, tomtom_timestamp_str: str, file_name_for_log: str
) -> dict:
    """Transforms the content of a single parsed TomTom FCD JSON file.

    Args:
       raw_data_from_tomtom_json : TomTom traffic flow data in JSON format.
       tomtom_timestamp_str : Timestamp of the observation.
       file_name_for_log : File name for logging.

    Returns:
        An aggregated dictionary based on the fcd data model.

    """
    transformed_items: dict = {"segmentId": {}}

    # Check if raw TomTom data is valid
    detailed_segments = raw_data_from_tomtom_json.get("detailedSegments")

    if not isinstance(detailed_segments, list):
        logger.warning(
            f"File '{file_name_for_log}' has 'detailedSegments' not as a list. Skipping."
        )
        return {}

    for segment_data in detailed_segments:
        if not isinstance(segment_data, dict):
            logger.warning(
                f"Skipping non-dictionary item in 'detailedSegments' of blob '{file_name_for_log}'."
            )
            continue

        segment_id_str = segment_data.get("segmentIdStr")
        if segment_id_str is None:
            segment_id_num = segment_data.get("segmentId")
            if segment_id_num is not None:
                segment_id_str = str(segment_id_num)
            else:
                logger.warning(
                    f"Skipping segment in blob '{file_name_for_log}' due to missing 'segmentId' or 'segmentIdStr'."
                )
                continue

        shape_coords = []
        shape_data = segment_data.get("shape")
        if isinstance(shape_data, list):
            for point in shape_data:
                if (
                    isinstance(point, dict)
                    and "longitude" in point
                    and "latitude" in point
                ):
                    try:
                        shape_coords.append(
                            [float(point["longitude"]), float(point["latitude"])]
                        )
                    except (ValueError, TypeError):
                        logger.warning(
                            f"Invalid coordinate data for segment {segment_id_str} in file '{file_name_for_log}'. Point: {point}"
                        )
                else:
                    logger.warning(
                        f"Malformed shape point for segment {segment_id_str} in file '{file_name_for_log}'. Point: {point}"
                    )
        else:
            logger.warning(
                f"Shape data for segment {segment_id_str} in file '{file_name_for_log}' is not a list."
            )

        current_segment_properties = {
            "fcd_coverage": convert_confidence_to_fcd_num(
                segment_data.get("confidence")
            ),
            "averageSpeed": segment_data.get("averageSpeed"),
            "typicalSpeed": segment_data.get("typicalSpeed"),
            "currentSpeed": segment_data.get("currentSpeed"),
            "confidence_level": segment_data.get("confidence"),
        }

        time_variant_payload = {
            "date": {tomtom_timestamp_str: {"properties": current_segment_properties}}
        }

        current_segment_geometry = {"type": "LineString", "coordinates": shape_coords}

        transformed_items["segmentId"][segment_id_str] = {
            "geometry": current_segment_geometry,
            "detailedSegment": time_variant_payload,
        }

    return transformed_items


def sort_tomtom_data_aggregation_file_by_date(tomtom_aggregation_file: dict) -> dict:
    """Function sorts the TomTom aggregation file by date.

    Args:
        tomtom_aggregation_file: TomTom aggregation file dictionary.

    Returns:
        A sorted (by date) aggregation dictionary

    """
    for segment_id, segment_data in tomtom_aggregation_file.get(
        "segmentId", {}
    ).items():
        if (
            "detailedSegment" in segment_data
            and "date" in segment_data["detailedSegment"]
        ):
            try:
                sorted_dates = sorted(
                    segment_data["detailedSegment"]["date"].items(),
                    key=lambda item: datetime.strptime(item[0], "%Y-%m-%dT%H:%M:%S"),
                )
                segment_data["detailedSegment"]["date"] = dict(sorted_dates)
            except ValueError as e:
                logger.warning(
                    f"Could not sort dates for segment {segment_id} due to parsing error: {e}"
                )

    return tomtom_aggregation_file


def update_tomtom_json_data_for_aggregation_file(
    new_tomtom_file: dict, tomtom_file_to_update: dict
) -> dict:
    """Updates the TomTom aggregation dictionary with the new aggregation dictionary.

    Args:
        new_tomtom_file: TomTom aggregation file dictionary.
        tomtom_file_to_update: TomTom aggregation dictionary.

    """
    num_tomtom_records = 0
    num_updated_tomtom_records = 0

    # Check if tomtom_file_to_update is empty, this happens when read_existing_json_records() function returns an empty Dictionary.
    # If so, return the new tomtom_file as the aggregated file.
    if not tomtom_file_to_update:
        tomtom_file_to_update = new_tomtom_file
    else:
        for segment_id_str, segment_values in new_tomtom_file["segmentId"].items():
            num_tomtom_records += 1

            if segment_id_str not in tomtom_file_to_update["segmentId"]:
                tomtom_file_to_update["segmentId"][segment_id_str] = {}
                tomtom_file_to_update["segmentId"][segment_id_str]["geometry"] = (
                    segment_values["geometry"]
                )
                tomtom_file_to_update["segmentId"][segment_id_str][
                    "detailedSegment"
                ] = {}
                tomtom_file_to_update["segmentId"][segment_id_str]["detailedSegment"][
                    "date"
                ] = {}

            for date_key, date_value in new_tomtom_file["segmentId"][segment_id_str][
                "detailedSegment"
            ]["date"].items():
                if (
                    date_key
                    not in tomtom_file_to_update["segmentId"][segment_id_str][
                        "detailedSegment"
                    ]["date"]
                ):
                    tomtom_file_to_update["segmentId"][segment_id_str][
                        "detailedSegment"
                    ]["date"][date_key] = date_value
                    num_updated_tomtom_records += 1

    if num_tomtom_records == 0:
        logger.info(
            "updatable file empty, returning new Tom Tom file as base for future aggregation"
        )
    else:
        logger.info(
            f"Tom Tom aggregation file updated. {num_tomtom_records} records scanned, of which {num_updated_tomtom_records} contained new records."
        )

    return tomtom_file_to_update

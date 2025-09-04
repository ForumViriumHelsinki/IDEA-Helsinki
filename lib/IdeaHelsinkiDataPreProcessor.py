#------------------------------------------------------#
#---------------- GENERAL IMPORTS ---------------------#
#------------------------------------------------------#
import pandas as pd
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

#------------------------------------------------------#
#-------------- PROJECT CLASS IMPORTS -----------------#
#------------------------------------------------------#
from classes.Logger import Logger

"""
    Library for IdeaHelsinkiRoadSegment class
"""

logger = Logger(__name__)

# Legacy function for storing IDEA profile/validation to disc.
def write_df_as_csv(df: pd.DataFrame, file_name: str, append: bool = False) -> bool:
    """
    Writes a pandas DataFrame to a CSV file. Can append to an existing file.

    Args:
        df: A Pandas DataFrame.
        file_name: Directory location for file saving.
        append: If True, appends to the file without a header if it exists.
                If False (default), overwrite the file.
    """
    if df.empty:
        logger.warning('DataFrame is empty, not writing to file.')
        return False

    if not file_name:
        logger.warning("File name is empty, not writing to file.")
        return False

    file_path = Path(file_name)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if append and file_path.exists():
            # Update file
            df.to_csv(file_path, mode='a', index=False, sep=';', header=False)
        else:
            # Overwrite file (default behavior)
            df.to_csv(file_path, mode='w', index=False, sep=';', header=True)

        logger.info(f'Successfully wrote DataFrame to CSV: {file_path}')
        return True
    except Exception as e:
        logger.error(f'Unexpected error writing CSV to {file_name}: {e}')
        return False

# Legacy function for removing IDEA profile/validation from disc.
def delete_csv(file_name: str) -> bool:
    """
    Deletes a CSV file from disk.
    Args:
        file_name: Directory location for file saving.
    Returns:
        True if the file was successfully deleted.
    """
    try:
        file_path = Path(file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        else:
            logger.error(f'File {file_name} does not exist')
            return False
    except OSError as e:
        logger.error(f"Error deleting file {file_name}: {e}")
        return False


def determine_disturbance_dates(reported_disturbances: list) -> tuple[datetime, datetime]:
    """
    Determines the earliest start date and latest end date for reported disturbances.

    Args:
        reported_disturbances: A List containing reported traffic disturbances.

    Returns:
            Earliest start (str) date and latest end date (str) found from the reported disturbances.
            If nothing was found or an error occurs, start date and end date default to the current time UTC (a class object does not perform the main loop).
    """

    earliest_start_date = datetime.now(timezone.utc)
    latest_end_date = earliest_start_date

    if len(reported_disturbances) > 0:
        try:
            earliest_start_date = min(datetime.strptime(c["properties"]["star_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc) for c in reported_disturbances)
            latest_end_date = max(datetime.strptime(c['properties']['end_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc) for c in reported_disturbances)
        except Exception as e:
            logger.error(f"Unexpected error while reading dates, {e}")

    return earliest_start_date, latest_end_date

def calculate_profiling_end_date(disturbance_start_date: datetime, lead_time_hours: int) -> datetime:
    """
    This function calculates the end date for a profiling.
    By design, it should be earlier than the disturbance start date (lead time defined in lead_time_hours),
    but it is not; the profiling end date is set to the current date UTC.

    Args:
        disturbance_start_date: The reported start date for disturbance.
        lead_time_hours: How many hours are subtracted from the start date to determine the profiling end date.

    Returns:
        The end date for profiling.

    """
    current_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    if (disturbance_start_date - timedelta(hours=lead_time_hours)) < (current_date - timedelta(hours=lead_time_hours)):
        return disturbance_start_date - timedelta(hours=lead_time_hours)
    else:
        return current_date

def calculate_profiling_start_date(profiling_end_date: datetime, profile_time_frame_weeks: int) -> datetime:
    """
    This function calculates the start date for profiling. IDEA specifies that this should be at least 6 months before the profiling end date.

    Args:
        profiling_end_date: The end date for profiling.
        profile_time_frame_weeks: How many weeks between profiling start and end date.
    Returns:
        The start date for profiling.
    """
    return profiling_end_date - timedelta(weeks=profile_time_frame_weeks)

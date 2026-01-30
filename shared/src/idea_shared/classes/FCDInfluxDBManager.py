import csv
import io
from datetime import UTC, datetime

import pandas as pd
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException
from urllib3.util.retry import Retry

from idea_shared.classes.Logger import Logger

# Default timeout reduced from 300s to 60s for faster failure detection
DEFAULT_TIMEOUT_MS = 60000


class FCDInfluxDBManager:
    """
    Manages writing and querying Floating Car Data (FCD) to InfluxDB.
    This class is specifically designed to work with the TFDS data models.

    Includes improved retry strategy with exponential backoff and jitter
    for better reliability under transient network failures.
    """

    def __init__(
        self, url: str, token: str, org: str, bucket: str, timeout: int = DEFAULT_TIMEOUT_MS
    ):
        self.client = None  # Initialize client to None
        try:
            # Initialize the connection to the InfluxDB client with enhanced retry strategy.
            # Timeout is in milliseconds (default: 60000ms = 1 minute)
            # Retry on common transient errors including connection issues
            retries = Retry(
                total=5,
                backoff_factor=1,
                # Add jitter to prevent thundering herd
                backoff_jitter=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                # Retry on connection-related errors
                allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
                raise_on_status=False,
            )
            self.client = InfluxDBClient(
                url=url, token=token, org=org, retries=retries, timeout=timeout
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            self.org = org
            self.bucket = bucket
            self.logger = Logger(__name__)
            self.logger.info(
                f"FCDInfluxDBManager initialized - URL: {url}, Org: {self.org}, Bucket: {self.bucket}, Timeout: {timeout}ms"
            )
        except (ApiException, ConnectionError, TimeoutError, OSError) as e:
            print(f"Failed to connect to InfluxDB: {e}")
            self.close()
            raise

    def __enter__(self):
        """
        This enables the class to be used in a "with" statement.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        This enables the class to be used in a "with" statement.
        """
        self.close()

    def check_connection(self) -> bool:
        """
        Check if the connection to the InfluxDB server is established.

        Returns:
            bool: True if connection is active, False otherwise.
        """
        try:
            if self.client and self.client.ping():
                self.logger.info("InfluxDB connection is active.")
                return True
            if not self.client:
                self.logger.error("InfluxDB client is not initialized.")
            else:
                self.logger.error(
                    f"InfluxDB ping failed. Check URL ({self.client.url}), token, and org ({self.org})."
                )
            return False
        except (ConnectionError, TimeoutError, OSError) as e:
            self.logger.error(
                f"InfluxDB connection check failed due to network error: {e}. "
                f"URL: {self.client.url if self.client else 'N/A'}"
            )
            return False
        except Exception as e:
            self.logger.error(f"InfluxDB connection check failed unexpectedly: {e}")
            return False

    def _write_batch(self, points: list, batch_number: int):
        """
        Write a batch of points with logging.

        Args:
            points: List of Point objects to write
            batch_number: Sequential batch number for logging
        """
        self.logger.info(f"Writing batch {batch_number} ({len(points)} points)...")
        self.write_api.write(bucket=self.bucket, org=self.org, record=points)
        self.logger.info(
            f"Successfully wrote batch {batch_number} - URL: {self.client.url}, "
            f"Org: {self.org}, Bucket: {self.bucket}"
        )

    def write_dataframe(
        self,
        df: pd.DataFrame,
        segment_id: str,
        measurement_name: str,
        batch_size: int = 5000,
    ):
        """
        Writes a pandas DataFrame to InfluxDB using incremental batching.

        The DataFrame must contain a 'time' column for the timestamp used in the IfluxDB.

        Args:
            df: The DataFrame to write. Must include a 'time' column.
            segment_id: The identifier for the segment, used as a tag.
            measurement_name: The name of the measurement to write to, example = "idea_validation".
            batch_size: Number of rows per batch (default: 5000, per InfluxDB best practices)
        """
        if df.empty:
            self.logger.warning("DataFrame is empty. Nothing to write.")
            return

        if "time" not in df.columns:
            self.logger.error("Error: DataFrame must contain a 'time' column.")
            raise ValueError("DataFrame missing 'time' column")

        df_copy = df.copy()

        # Ensure the time column is a datetime object
        if not pd.api.types.is_datetime64_any_dtype(df_copy["time"]):
            self.logger.warning("'time' column is not a datetime type. Converting...")
            df_copy["time"] = pd.to_datetime(df_copy["time"])

        # Ensure the datetime object is timezone-aware
        if df_copy["time"].dt.tz is None:
            self.logger.warning("'time' column is timezone-naive. Forcing to UTC.")
            df_copy["time"] = df_copy["time"].dt.tz_localize("UTC")

        # Add the segment_id as a column to be used as a tag
        df_copy["segmentId"] = segment_id

        total_rows = len(df_copy)
        num_batches = (total_rows + batch_size - 1) // batch_size  # Ceiling division

        if num_batches > 1:
            self.logger.info(
                f"Writing {total_rows} rows in {num_batches} batches for segmentId '{segment_id}'"
            )

        # Write DataFrame in batches
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_rows)
            df_batch = df_copy.iloc[start_idx:end_idx]

            try:
                self.write_api.write(
                    bucket=self.bucket,
                    record=df_batch,
                    data_frame_measurement_name=measurement_name,
                    data_frame_tag_columns=["segmentId"],
                    data_frame_timestamp_column="time",
                )
                if num_batches > 1:
                    self.logger.info(
                        f"Successfully wrote batch {batch_num + 1}/{num_batches} "
                        f"({len(df_batch)} rows) for segmentId '{segment_id}'"
                    )
            except Exception as e:
                self.logger.error(
                    f"Writing DataFrame batch {batch_num + 1}/{num_batches} to InfluxDB failed. {e}"
                )
                raise

        # Final summary log
        self.logger.info(
            f"Completed: {total_rows} rows written to measurement '{measurement_name}' "
            f"for segmentId '{segment_id}' - URL: {self.client.url}, Org: {self.org}, Bucket: {self.bucket}"
        )

    def write_fcd_model(self, fcd_data: dict, batch_size: int = 5000):
        """
        Writes the TFDS FCD data model to InfluxDB using incremental batching.

        Args:
            fcd_data: Dictionary of FCD segment data.
            batch_size: Number of points per batch (default: 5000, per InfluxDB best practices)
        """
        segments = fcd_data.get("segmentId", {})
        total_segments = len(segments)
        self.logger.info(
            f"Processing {total_segments} segments for InfluxDB write (batch size: {batch_size})"
        )

        current_batch = []
        total_points_written = 0
        batch_number = 0

        for idx, (segment_id, segment_details) in enumerate(segments.items(), 1):
            observations = segment_details.get("detailedSegment", {}).get("date", {})

            for timestamp_str, observation_data in observations.items():
                properties = observation_data.get("properties", {})
                if not properties:
                    continue
                try:
                    dt_object = (
                        datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if timestamp_str.endswith("Z")
                        else datetime.fromisoformat(timestamp_str).replace(tzinfo=UTC)
                    )
                except ValueError:
                    self.logger.warning(
                        f"Could not parse timestamp '{timestamp_str}'. Skipping."
                    )
                    continue
                point = (
                    Point("segment_data").tag("segmentId", segment_id).time(dt_object)
                )
                for key, value in properties.items():
                    if isinstance(value, int | float | str | bool):
                        point.field(key, value)
                current_batch.append(point)

                # Write batch when it reaches the specified size
                if len(current_batch) >= batch_size:
                    batch_number += 1
                    try:
                        self._write_batch(current_batch, batch_number)
                        total_points_written += len(current_batch)
                        current_batch = []  # Free memory
                    except Exception as e:
                        self.logger.error(
                            f"Writing batch {batch_number} to InfluxDB failed. {e}"
                        )
                        raise

            # Log progress every 10 segments
            if idx % 10 == 0:
                self.logger.info(
                    f"Processed {idx}/{total_segments} segments ({total_points_written} points written)"
                )

        # Write remaining points
        if current_batch:
            batch_number += 1
            try:
                self._write_batch(current_batch, batch_number)
                total_points_written += len(current_batch)
            except Exception as e:
                self.logger.error(
                    f"Writing final batch {batch_number} to InfluxDB failed. {e}"
                )
                raise

        if total_points_written == 0:
            self.logger.info("No points to write.")
        else:
            self.logger.info(
                f"Completed: {total_points_written} points written in {batch_number} batches"
            )

    def get_last_update_timestamp(self) -> datetime | None:
        """
        Queries the InfluxDB database for the latest timestamp.

        NOTE! This returns the latest update timestamp of a measurement, not the timestamp then it was uploaded to InfluxDB.
        This is used to determine how "late" the database is.

        Returns:
            Timestamp of the latest measurement or None if no measurements were found (the bucket is empty).
        """
        flux_query = f'from(bucket: "{self.bucket}") |> range(start: 0) |> filter(fn: (r) => r._measurement == "segment_data") |> last() |> keep(columns: ["_time"])'
        try:
            tables = self.query_api.query(query=flux_query, org=self.org)
            if tables and tables[0].records:
                return tables[0].records[0].get_time()
            return None
        except Exception as e:
            self.logger.error(f"Querying last timestamp failed. {e}")
            raise

    def get_segment_update_timestamp(
        self,
        segment_id: str,
        measurement_name: str,
        first_or_last: str,
        interval_minutes: int | None = None,
    ) -> datetime | None:
        """
        Queries the InfluxDB database for the first or last timestamp for a particular segment in a particular measurement.

        segment_id (str): The ID of the segment to query.
        measurement_name (str): The name of the measurement to query.
        first_or_last (str): String variable => "first" or "last"
        interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.). If none, no time aggregation is performed.

        Returns:
            Timestamp of the measurement for the segment or None if no measurements were found (the segment is not in the database).
        """
        query_parts = [
            f'from(bucket: "{self.bucket}")',
            "|> range(start: 0)",
            f'|> filter(fn: (r) => r._measurement == "{measurement_name}" and r.segmentId == "{segment_id}")',
        ]
        if interval_minutes and interval_minutes > 0:
            query_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: last, createEmpty: false)"
            )

        query_parts.extend([f"|> {first_or_last}()", '|> keep(columns: ["_time"])'])

        flux_query = " ".join(query_parts)

        try:
            tables = self.query_api.query(query=flux_query, org=self.org)
            if tables and tables[0].records:
                return tables[0].records[0].get_time()
            return None
        except Exception as e:
            self.logger.error(f"Querying last timestamp failed.{e}")
            raise

    def get_last_segment_update_timestamp(
        self,
        segment_id: str,
        measurement_name: str,
        interval_minutes: int | None = None,
    ) -> datetime | None:
        """
        Queries the InfluxDB database for the latest timestamp for a particular segment.

        NOTE! This returns the latest update timestamp of a measurement, not the timestamp then it was uploaded to InfluxDB.

        segment_id (str): The ID of the segment to query.
        measurement_name (str): The name of the measurement to query.
        interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.). If none, no time aggregation is performed.

        Returns:
            Timestamp of the latest measurement for the segment or None if no measurements were found (the segment is not in the database).
        """
        return self.get_segment_update_timestamp(
            segment_id=segment_id,
            measurement_name=measurement_name,
            first_or_last="last",
            interval_minutes=interval_minutes,
        )

    def get_first_segment_update_timestamp(
        self,
        segment_id: str,
        measurement_name: str,
        interval_minutes: int | None = None,
    ) -> datetime | None:
        """
        Queries the InfluxDB database for the first (earliest) timestamp for a particular segment.

        NOTE! This returns the latest update timestamp of a measurement, not the timestamp then it was uploaded to InfluxDB.

        segment_id (str): The ID of the segment to query.
        measurement_name (str): The name of the measurement to query.
        interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.). If none, no time aggregation is performed.

        Returns:
            Timestamp of the first measurement for the segment or None if no measurements were found (the segment is not in the database).
        """

        return self.get_segment_update_timestamp(
            segment_id=segment_id,
            measurement_name=measurement_name,
            first_or_last="first",
            interval_minutes=interval_minutes,
        )

    def get_segment_data_csv(
        self,
        segment_id: str,
        measurement_name: str,
        start_time: datetime = None,
        end_time: datetime = None,
        latest_only: bool = False,
        query_fields: list | None = None,
        interval_minutes: int | None = None,
    ) -> str | None:
        """
        Queries the InfluxDB database for measurements from a segment. NOTE, this queries ALL data in the measurements.

        Args:
            segment_id (str): The ID of the segment to query.
            measurement_name (str): The name of the measurement to query.
            start_time (datetime): The start time of the query. If None, the query will be done from the earliest measurement timestamp.
            end_time (datetime): The end time of the query. If None, the query will be done from the latest measurement timestamp.
            latest_only (bool): If True, the query will return only the latest measurement.
            query_fields: A list of specific fields to query. If None or empty, all fields are returned.
            interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.).

        Returns:
            A CSV formated string for the found measurements or None if nothing was found.
        """
        query_body_parts = [f'from(bucket: "{self.bucket}")']

        if latest_only:
            query_body_parts.append("|> range(start: 0)")
        else:
            start = start_time.isoformat() if start_time else "0"
            stop_part = f", stop: {end_time.isoformat()}" if end_time else ""
            query_body_parts.append(f"|> range(start: {start}{stop_part})")

        query_body_parts.extend(
            [
                f'|> filter(fn: (r) => r._measurement == "{measurement_name}")',
                f'|> filter(fn: (r) => r.segmentId == "{segment_id}")',
            ]
        )

        # Determine if there are specific fields targeted in the query
        if query_fields:
            field_conditions = [f'r._field == "{field}"' for field in query_fields]
            filter_logic = " or ".join(field_conditions)
            query_body_parts.append(f"|> filter(fn: (r) => {filter_logic})")

        if interval_minutes and interval_minutes > 0:
            query_body_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: last, createEmpty: false)"
            )

        if latest_only:
            query_body_parts.append("|> last()")
        else:
            query_body_parts.append('|> sort(columns: ["_time"])')

        query_body_parts.append(
            '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
        )

        flux_query = "".join(query_body_parts)

        try:
            return self._query_to_csv(flux_query)
        except Exception as e:
            self.logger.error(f"An error occurred during segment data query. {e}")
            raise e

    def get_segment_data_dataframe(
        self,
        segment_id: str,
        measurement_name: str,
        start_time: datetime = None,
        end_time: datetime = None,
        latest_only: bool = False,
        query_fields: list | None = None,
        interval_minutes: int | None = None,
    ) -> pd.DataFrame | None:
        """
        Queries InfluxDB for segment data and returns it as a Pandas DataFrame.

        Args:
            segment_id: The ID of the FCD segment to query.
            measurement_name: The name of the measurement.
            start_time: The start time for the query. If None, the query will be done from the earliest measurement timestamp.
            end_time: The end time for the query. If None, the query will be done from the latest measurement timestamp.
            latest_only: If True, returns only the most recent data point.
            query_fields: A list of specific fields to query. If None or empty, all fields are returned.
            interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.).

        Returns:
            A Pandas DataFrame containing the queried data, or None if an error occurs.
        """
        query_body_parts = [f'from(bucket: "{self.bucket}")']

        if latest_only:
            query_body_parts.append("|> range(start: 0)")
        else:
            start = start_time.isoformat() if start_time else "0"
            stop_part = f", stop: {end_time.isoformat()}" if end_time else ""
            query_body_parts.append(f"|> range(start: {start}{stop_part})")

        query_body_parts.extend(
            [
                f'|> filter(fn: (r) => r._measurement == "{measurement_name}")',
                f'|> filter(fn: (r) => r.segmentId == "{segment_id}")',
            ]
        )

        # Determine if there are specific fields targeted in the query
        if query_fields:
            field_conditions = [f'r._field == "{field}"' for field in query_fields]
            filter_logic = " or ".join(field_conditions)
            query_body_parts.append(f"|> filter(fn: (r) => {filter_logic})")

        if interval_minutes and interval_minutes > 0:
            query_body_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: last, createEmpty: false)"
            )

        if latest_only:
            query_body_parts.append("|> last()")
        else:
            query_body_parts.append('|> sort(columns: ["_time"])')

        query_body_parts.append(
            '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")'
        )

        flux_query = "".join(query_body_parts)

        try:
            df = self.query_api.query_data_frame(flux_query)
            if df is not None and not df.empty and query_fields:
                query_fields.insert(0, "_time")
                df = df[query_fields]
            return df
        except Exception as e:
            self.logger.error(f"An error occurred during segment data query. {e}")
            raise e

    def _query_to_csv(self, query: str) -> str | None:
        """
        Internal helper to execute a Flux query and return the result as a CSV string.
        """
        try:
            csv_rows_generator = self.query_api.query_csv(query, org=self.org)
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerows(csv_rows_generator)
            return output.getvalue()
        except Exception as e:
            self.logger.error(f"Error executing query.{e} ")
            raise e

    def close(self):
        """
        Closes the InfluxDB client.
        """
        if self.client:
            self.client.close()
            self.logger.info("InfluxDB client closed.")

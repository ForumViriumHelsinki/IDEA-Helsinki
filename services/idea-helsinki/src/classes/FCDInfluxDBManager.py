import io
import csv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.rest import ApiException
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime, timezone
from urllib3.util.retry import Retry
import pandas as pd

from classes.Logger import Logger

class FCDInfluxDBManager:
    """
    Manages writing and querying Floating Car Data (FCD) to InfluxDB.
    This class is specifically designed to work with the TFDS data models.
    """
    def __init__(self, url: str, token: str, org: str, bucket: str):
        self.client = None # Initialize client to None
        try:
            # Initialize the connection to the InfluxDB client with a retry strategy.
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            self.client = InfluxDBClient(url=url, token=token, org=org, retries=retries)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            self.org = org
            self.bucket = bucket
            self.logger = Logger(__name__)
            self.logger.info(f"FCDInfluxDBManager initialized for bucket '{self.bucket}'.")
        except (ApiException, ConnectionError) as e:
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
        """"
        This function checks if the connection to the InfluxDB server is established.
        """
        try:
            if self.client and self.client.ping():
                self.logger.info("InfluxDB connection is active.")
                return True
            return False
        except Exception as e:
            self.logger.error(f"InfluxDB connection check failed. {e}")
            return False

    def write_dataframe(self, df: pd.DataFrame, segment_id: str, measurement_name: str):
        """
        Writes a pandas DataFrame to InfluxDB.

        The DataFrame must contain a 'time' column for the timestamp used in the IfluxDB.

        Args:
            df : The DataFrame to write. Must include a 'time' column.
            segment_id : The identifier for the segment, used as a tag.
            measurement_name : The name of the measurement to write to, example = "idea_validation".
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
        try:
            self.write_api.write(
                bucket=self.bucket,
                record=df_copy,
                data_frame_measurement_name=measurement_name,
                data_frame_tag_columns=["segmentId"],
                data_frame_timestamp_column="time",
            )
            self.logger.info(f"Successfully wrote {len(df_copy)} rows to measurement '{measurement_name}' for segmentId '{segment_id}'.")
        except Exception as e:
            self.logger.error(f"Writing DataFrame to InfluxDB failed. {e}")
            raise

    def write_fcd_model(self, fcd_data: dict):
        """
        Writes the TFDS FCD data model to InfluxDB.

        Args:
            fcd_data : Dictionary of FCD segment data.
        """
        points = []
        segments = fcd_data.get("segmentId", {})
        for segment_id, segment_details in segments.items():
            observations = segment_details.get("detailedSegment", {}).get("date", {})
            for timestamp_str, observation_data in observations.items():
                properties = observation_data.get("properties", {})
                if not properties: continue
                try:
                    dt_object = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')) if timestamp_str.endswith('Z') else datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    self.logger.warning(f"Could not parse timestamp '{timestamp_str}'. Skipping.")
                    continue
                point = Point("segment_data").tag("segmentId", segment_id).time(dt_object)
                for key, value in properties.items():
                    if isinstance(value, (int, float, str, bool)):
                        point.field(key, value)
                points.append(point)

        if not points:
            self.logger.info("No points to write.")
            return
        try:
            self.write_api.write(bucket=self.bucket, org=self.org, record=points)
            self.logger.info(f"Successfully wrote {len(points)} points to bucket '{self.bucket}'.")
        except Exception as e:
            self.logger.error(f"Writing to InfluxDB failed. {e}")
            raise

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

    def get_last_segment_update_timestamp(self, segment_id: str, interval_minutes: int | None = None) -> datetime | None:
        """
        Queries the InfluxDB database for the latest timestamp for a particular segment.

        NOTE! This returns the latest update timestamp of a measurement, not the timestamp then it was uploaded to InfluxDB.
        This is used to determine the "validation" start point for a segment.

        Returns:
            Timestamp of the latest measurement for the segment or None if no measurements were found (the segment is not in the database).
        """
        query_parts = [
            f'from(bucket: "{self.bucket}")',
            "|> range(start: 0)",
            f'|> filter(fn: (r) => r._measurement == "segment_data" and r.segmentId == "{segment_id}")',
        ]
        if interval_minutes and interval_minutes > 0:
            query_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: last, createEmpty: false)"
            )

        query_parts.extend(["|> last()", '|> keep(columns: ["_time"])'])

        flux_query = " ".join(query_parts)

        try:
            tables = self.query_api.query(query=flux_query, org=self.org)
            if tables and tables[0].records:
                return tables[0].records[0].get_time()
            return None
        except Exception as e:
            self.logger.error(f"Querying last timestamp failed.{e}")
            raise

    def get_first_segment_update_timestamp(self, segment_id: str, interval_minutes: int | None = None) -> datetime | None:
        """
        Queries the InfluxDB database for the first (earliest) timestamp for a particular segment.

        NOTE! This returns the latest update timestamp of a measurement, not the timestamp then it was uploaded to InfluxDB.
        This is used to determine if the segment can be profiled per the IDEA timeframe requirements.

        Returns:
            Timestamp of the first measurement for the segment or None if no measurements were found (the segment is not in the database).
        """
        query_parts = [
            f'from(bucket: "{self.bucket}")',
            "|> range(start: 0)",
            f'|> filter(fn: (r) => r._measurement == "segment_data" and r.segmentId == "{segment_id}")',
        ]
        if interval_minutes and interval_minutes > 0:
            query_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: first, createEmpty: false)"
            )

        query_parts.extend(["|> first()", '|> keep(columns: ["_time"])'])

        flux_query = " ".join(query_parts)

        try:
            tables = self.query_api.query(query=flux_query, org=self.org)
            if tables and tables[0].records:
                return tables[0].records[0].get_time()
            return None
        except Exception as e:
            self.logger.error(f"Querying last timestamp for segment '{segment_id}' failed. {e}")
            raise

    def get_segment_data_idea_format(self, segment_id: str, start_time: datetime = None, end_time: datetime = None, latest_only: bool = False, interval_minutes: int | None = None) -> str | None:
        """
        Queries the InfluxDB database for measurements from a segment. NOTE, this is an IDEA specific query.

        Args:
            segment_id (str): The ID of the segment to query.
            start_time (datetime): The start time of the query. If None, the query will be done from the earliest measurement timestamp.
            end_time (datetime): The end time of the query. If None, the query will be done from the latest measurement timestamp.
            latest_only (bool): If True, the query will return only the latest measurement.
            interval_minutes (int): The interval for the measurements (every minute, 5 minutes, etc.).

        Returns:
            An IDEA specific formated string for the found measurements to be used in the IDEA algorithm or None if nothing was found.
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
                '|> filter(fn: (r) => r._measurement == "segment_data")',
                f'|> filter(fn: (r) => r.segmentId == "{segment_id}")',
                '|> filter(fn: (r) => r._field == "fcd_coverage")',
            ]
        )

        if interval_minutes and interval_minutes > 0:
            query_body_parts.append(
                f"|> aggregateWindow(every: {interval_minutes}m, fn: last, createEmpty: false)"
            )

        if latest_only:
            query_body_parts.append("|> last()")
        else:
            query_body_parts.append('|> sort(columns: ["_time"])')

        query_body_parts.append('|> keep(columns: ["_time", "_value"])')
        flux_query = "\n".join(query_body_parts)

        try:
            tables = self.query_api.query(query=flux_query, org=self.org)
            lines = []
            for table in tables:
                for record in table.records:
                    timestamp_formatted = (
                        record.get_time().strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
                    )
                    coverage = record.get_value()
                    lines.append(f"{timestamp_formatted};{coverage}")
            return "\n".join(lines)
        except Exception as e:
            self.logger.error(f"An error occurred during segment profile query. {e}")
            raise e

    def get_segment_data_csv(self, segment_id: str, start_time: datetime = None, end_time: datetime = None, latest_only: bool = False) -> str | None:
        """
        Queries the InfluxDB database for measurements from a segment. NOTE, this queries ALL data in the measurements.

        Args:
            segment_id (str): The ID of the segment to query.
            start_time (datetime): The start time of the query. If None, the query will be done from the earliest measurement timestamp.
            end_time (datetime): The end time of the query. If None, the query will be done from the latest measurement timestamp.
            latest_only (bool): If True, the query will return only the latest measurement.

        Returns:
            A CSV formated string for the found measurements or None if nothing was found.
        """
        query_header = 'import "date"\n\n'
        query_body_parts = [f'from(bucket: "{self.bucket}")']

        if latest_only:
            query_body_parts.append("|> range(start: 0)")
        else:
            start = start_time.isoformat() if start_time else "0"
            stop_part = f", stop: {end_time.isoformat()}" if end_time else ""
            query_body_parts.append(f"|> range(start: {start}{stop_part})")

        query_body_parts.extend(
            [
                '|> filter(fn: (r) => r._measurement == "segment_data")',
                f'|> filter(fn: (r) => r.segmentId == "{segment_id}")',
                '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")',
            ]
        )

        if latest_only:
            query_body_parts.append("|> last()")
        else:
            query_body_parts.append('|> sort(columns: ["_time"])')

        query_body_parts.append(
            '|> map(fn: (r) => ({ r with _time: date.format(t: r._time, format: "yyyy-MM-dd HH:mm:ssXXX") }))'
        )
        flux_query = query_header + "\n".join(query_body_parts)

        try:
            return self._query_to_csv(flux_query)
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
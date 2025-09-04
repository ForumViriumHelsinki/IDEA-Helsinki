# ------------------------------------------------------#
# ---------------- GENERAL IMPORTS ---------------------#
# ------------------------------------------------------#
from datetime import datetime, timedelta, timezone
from enum import Enum
from azure.storage.blob import BlobServiceClient, BlobProperties

# ------------------------------------------------------#
# -------------- PROJECT CLASS IMPORTS -----------------#
# ------------------------------------------------------#
from idea_shared.classes.Logger import Logger


class TimePrecision(Enum):
    """Defines the precision for the blob name prefix searches."""

    DAY = "%Y-%m-%d"
    HOUR = "%Y-%m-%dT%H"
    MINUTE = "%Y-%m-%dT%H:%M"


class AzureBlobContainerManager:
    """
    Manages operations for a specific Azure Blob Storage container using a SAS token.

    args:
        account_name : Azure account name
        container_name: Azure Blob storage container name
        sas_token: Access token for the storage container, this class assumes that the SAS token only has read rights.
    """

    def __init__(self, account_name: str, container_name: str, sas_token: str):
        self.account_name = account_name
        self.container_name = container_name
        self.sas_token = sas_token
        self.logger = Logger(__name__)

        account_url = f"https://{self.account_name}.blob.core.windows.net"

        try:
            self.blob_service_client = BlobServiceClient(
                account_url=account_url, credential=self.sas_token
            )
            self.container_client = self.blob_service_client.get_container_client(
                self.container_name
            )

            self.logger.info(
                f"Successfully connected to container '{container_name}' in account '{account_name}'."
            )
        except Exception as e:
            self.logger.error(
                f"Failed to initialize client for account '{account_name}', container '{container_name}'. Error: {e}"
            )

    def __str__(self) -> str:
        return (
            f"AzureBlobContainerManager(account_name='{self.account_name}', "
            f"container_name='{self.container_name}', sas_token_provided=True)"
        )

    def list_blobs(
        self, name_starts_with: str | None = None, include_metadata: bool = False
    ):
        """
        Lists all the blobs in the container

        Args:
            name_starts_with = a prefix for the blobs listed. Note that if the container has folders, it must be included in the prefix => "folder"/blob name
            include_metadata = Include blob metadata (last modified etc.)

        Returns:
            A list of blobs (all or marched ones)
        """
        try:
            self.logger.info(
                f"Listing blobs in '{self.container_name}' with prefix '{name_starts_with}'."
            )
            return self.container_client.list_blobs(
                name_starts_with=name_starts_with,
                include="metadata" if include_metadata else None,
            )
        except Exception as e:
            self.logger.error(
                f"Failed to list blobs in container '{self.container_name}'. Error: {e}"
            )

    def get_latest_blob(self):
        """
        Get the latest blob from the container, based on metadata last modified date.
        """
        try:
            blob_list = list(self.list_blobs(include_metadata=True))
            if not blob_list:
                self.logger.info(
                    f"Container '{self.container_name}' is empty or no blobs found."
                )
                return None
            latest_blob = max(blob_list, key=lambda blob: blob.last_modified)
            self.logger.info(
                f"Latest blob in '{self.container_name}': {latest_blob.name} (modified: {latest_blob.last_modified})."
            )
            return latest_blob
        except Exception as e:
            self.logger.error(
                f"Error finding latest blob in container '{self.container_name}'. Error: {e}"
            )

    def get_first_blob(self):
        """
        Get the first blob from the container, based on metadata last modified date.
        """
        try:
            blob_list = list(self.list_blobs(include_metadata=True))
            if not blob_list:
                self.logger.info(
                    f"Container '{self.container_name}' is empty or no blobs found."
                )
                return None
            first_blob = min(blob_list, key=lambda blob: blob.last_modified)
            self.logger.info(
                f"First blob in '{self.container_name}': {first_blob.name} (modified: {first_blob.last_modified})."
            )
            return first_blob
        except Exception as e:
            self.logger.error(
                f"Error finding latest blob in container '{self.container_name}'. Error: {e}"
            )

    def download_blob_content(self, blob_name: str) -> bytes | None:
        """
        Download the blob content of a single blob.

        Args:
            blob_name: the name of the blob to download. NOTE! If the container has folders, it must be included in the prefix => "folder"/blob name

        Returns:
            blob content in bytes
        """
        try:
            self.logger.debug(f"Downloading content of blob '{blob_name}' into memory.")
            blob_client = self.container_client.get_blob_client(blob_name)
            content = blob_client.download_blob().readall()
            self.logger.info(
                f"Successfully downloaded content of '{blob_name}' ({len(content)} bytes)."
            )
            return content
        except Exception as e:
            self.logger.error(
                f"Failed to download blob content for '{blob_name}'. Error: {e}"
            )
            return None

    def get_blobs_by_prefix(
        self, dt: datetime, precision: TimePrecision, folder_path: str | None = None
    ) -> list[BlobProperties]:
        """
        Finds blobs using a server-side prefix search based on a datetime and specified precision (day, hour, or minute).
        This only works if the blob names start with a timestamp (ISO format).

        Args:
            dt: The datetime to use for the search.
            precision: The level of precision (TimePrecision.DAY, .HOUR, or .MINUTE).
            folder_path: The folder path relative to the container root.

        Returns:
            A list of matching blob properties.
        """
        # Format the datetime into prefix string, example: "2025-04-07T23-50"
        time_prefix = dt.strftime(precision.value)

        # If the blob storage contains folders, add the folder string to the search prefix.
        if folder_path:
            full_prefix = f"{folder_path.strip('/')}/{time_prefix}"
        else:
            full_prefix = time_prefix

        self.logger.info(f"Searching for blobs with prefix: '{full_prefix}'")

        try:
            blob_list = list(
                self.container_client.list_blobs(name_starts_with=full_prefix)
            )
            self.logger.info(
                f"Found {len(blob_list)} blobs with prefix '{full_prefix}'."
            )
            return blob_list
        except Exception as e:
            self.logger.error(
                f"Failed to get blobs for prefix '{full_prefix}'. Error: {e}"
            )
            return []

    def get_blobs_in_range(
        self, start_time: datetime, end_time: datetime
    ) -> list[BlobProperties]:
        """
        Finds blobs within a datetime range by first using a date-based prefix search to narrow the results before final filtering.
        This function is not "precise", since it will search thought all the containers folders (if there is any).
        This only works if the blob names start with a timestamp (ISO format).

        Args:
            start_time: The start of the datetime range.
            end_time: The end of the datetime range.

        Returns:
            A sorted list of matching blob properties.
        """
        if start_time > end_time:
            self.logger.error("Start time cannot be after end time.")
            raise ValueError("Start time cannot be after end time.")

        # Determine the unique days the range spans (e.g., today and yesterday)
        days_to_check = {
            start_time.date() + timedelta(days=n)
            for n in range((end_time.date() - start_time.date()).days + 1)
        }

        self.logger.info(
            f"Searching for blobs in range: {start_time} to {end_time} across all prefixes."
        )

        search_prefixes = self.get_search_prefixes()
        if not search_prefixes:
            self.logger.warning("No search prefixes (folders or root files) found.")
            return []

        matched_blobs = []
        for prefix_item in search_prefixes:
            for day in sorted(list(days_to_check)):
                if prefix_item is None:
                    # The container has no folders.
                    prefix = day.strftime(TimePrecision.DAY.value)
                else:
                    # Surprise, the container has folders.
                    prefix = f"{prefix_item}/{day.strftime(TimePrecision.DAY.value)}"

                blobs_for_day = self.container_client.list_blobs(
                    name_starts_with=prefix
                )

                for blob in blobs_for_day:
                    try:
                        # Extract filename from fullpath before splitting
                        # Note that the filename is an ISO formated date.
                        filename = blob.name.split("/")[-1]
                        timestamp_str = filename.split(".")[0]

                        # Get the timestamp
                        blob_dt = datetime.strptime(
                            timestamp_str, "%Y-%m-%dT%H:%M:%S"
                        ).replace(tzinfo=timezone.utc)

                        if start_time <= blob_dt <= end_time:
                            matched_blobs.append(blob)
                    except (ValueError, IndexError):
                        continue

        self.logger.info(
            f"Scan complete. Found {len(matched_blobs)} blobs in the specified range."
        )
        matched_blobs.sort(key=lambda b: b.name)
        return matched_blobs

    def get_search_prefixes(self) -> list[str | None]:
        """
        Discovers top-level folders and checks for blobs in the root directory.

        Returns:
            A list of search prefixes. Folder names are returned as strings.
            If blobs exist in the root, a None value is included in the list.
        """
        self.logger.info("Discovering search prefixes (folders and root)...")
        prefixes: list[str | None] = []
        root_blobs_found = False
        try:
            # Walk_blobs method to find folders from the container.
            pages = self.container_client.walk_blobs(delimiter="/")
            for page in pages:
                if "/" in page.name:
                    # A folder in the container.
                    prefixes.append(page.name.strip("/"))
                else:
                    # A blob in the container root directory.
                    root_blobs_found = True

            if root_blobs_found:
                prefixes.append(None)

            self.logger.info(f"Found {len(prefixes)} search prefixes to check.")
            return prefixes
        except Exception as e:
            self.logger.error(f"Failed to discover search prefixes. Error: {e}")
            return []

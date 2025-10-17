"""
Streaming FCD blob processing module.

This module provides batch-based streaming processing of Azure blobs to prevent
memory exhaustion when processing large date ranges with multiple worker threads.
"""

import logging
from collections.abc import Generator
from datetime import datetime

import idea_shared.lib.FcdUtils as FcdUtils
import idea_shared.lib.TomTomFcdAggregator as TomTomFcdAggregator
from idea_shared.classes.AzureBlobContainerManager import AzureBlobContainerManager

logger = logging.getLogger(__name__)


def process_date_range_streaming(
    azure_manager: AzureBlobContainerManager,
    start_date: datetime,
    end_date: datetime,
    batch_size: int = 50,
) -> Generator[dict, None, None]:
    """
    Process Azure blobs for a date range in batches, yielding processed data incrementally.

    This function processes blobs in batches instead of loading everything into memory,
    allowing for bounded memory usage even with large date ranges and multiple workers.

    Args:
        azure_manager: Azure blob storage manager instance
        start_date: Start date for blob retrieval
        end_date: End date for blob retrieval
        batch_size: Number of blobs to process per batch (default: 50)

    Yields:
        dict: Processed and aggregated FCD data for each batch

    Example:
        >>> azure_manager = AzureBlobContainerManager(...)
        >>> for batch_data in process_date_range_streaming(
        ...     azure_manager,
        ...     datetime(2025, 1, 1),
        ...     datetime(2025, 1, 2),
        ...     batch_size=50
        ... ):
        ...     # Write batch_data to InfluxDB
        ...     influx_manager.write_fcd_model(batch_data)
    """
    # Get all blobs in the date range
    blobs_to_process = azure_manager.get_blobs_in_range(start_date, end_date)

    if not blobs_to_process:
        logger.info(
            f"No blobs found for date range {start_date.date()} to {end_date.date()}"
        )
        return

    total_blobs = len(blobs_to_process)
    logger.info(
        f"Processing {total_blobs} blobs in batches of {batch_size} "
        f"for date range {start_date.date()} to {end_date.date()}"
    )

    # Process blobs in batches
    for batch_start_idx in range(0, total_blobs, batch_size):
        batch_end_idx = min(batch_start_idx + batch_size, total_blobs)
        batch_blobs = blobs_to_process[batch_start_idx:batch_end_idx]

        logger.debug(
            f"Processing batch {batch_start_idx // batch_size + 1}: "
            f"blobs {batch_start_idx + 1}-{batch_end_idx} of {total_blobs}"
        )

        # Process this batch
        batch_data = _process_blob_batch(batch_blobs, azure_manager)

        # Only yield if we have data
        if batch_data:
            yield batch_data
        else:
            logger.debug(
                f"Batch {batch_start_idx // batch_size + 1} produced no data, skipping"
            )


def _process_blob_batch(blobs: list, azure_manager: AzureBlobContainerManager) -> dict:
    """
    Process a batch of blobs and return aggregated FCD data.

    Args:
        blobs: List of blob objects to process
        azure_manager: Azure blob storage manager instance

    Returns:
        dict: Aggregated FCD data for the batch
    """
    aggregated_fcd_data = {}

    for i, blob in enumerate(blobs):
        blob_name = blob.name
        logger.debug(f"Processing blob {i + 1}/{len(blobs)}: '{blob_name}'")

        # Get the blob timestamp from the blob name
        blob_timestamp_str = FcdUtils.extract_timestamp_str_from_file_name(blob_name)
        if blob_timestamp_str is None:
            logger.warning(
                f"Skipping blob '{blob_name}' due to inability to extract timestamp."
            )
            continue

        # Download the blob
        blob_content_bytes = azure_manager.download_blob_content(blob_name)
        if blob_content_bytes is None:
            logger.warning(
                f"Skipping blob '{blob_name}', download returned no content."
            )
            continue

        # Parse the blob content to a JSON dictionary
        blob_raw_data = FcdUtils.parse_json_from_bytes(blob_content_bytes)
        if blob_raw_data is None:
            logger.warning(
                f"Skipping blob '{blob_name}', downloaded content could not be parsed."
            )
            continue

        # Transform the blob raw data to the FCD data model
        transformed_items = (
            TomTomFcdAggregator.transform_single_tomtom_json_data_for_aggregation(
                blob_raw_data, blob_timestamp_str, blob_name
            )
        )

        # Aggregate the transformed blob raw data
        aggregated_fcd_data = (
            TomTomFcdAggregator.update_tomtom_json_data_for_aggregation_file(
                transformed_items, aggregated_fcd_data
            )
        )

    # Sort the aggregated data by date before returning
    if aggregated_fcd_data:
        return TomTomFcdAggregator.sort_tomtom_data_aggregation_file_by_date(
            aggregated_fcd_data
        )

    return {}

"""GCS Object API sync layer for cross-service data sharing.

Replaces GCS FUSE with explicit upload/download via the GCS Object API.
Uses ETag caching to skip redundant downloads and tenacity for retry
with exponential backoff on transient GCS errors.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.api_core import exceptions as gcs_exceptions
from google.auth.credentials import Credentials
from google.cloud import storage
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

_TRANSIENT_GCS_EXCEPTIONS = (
    gcs_exceptions.ServiceUnavailable,
    gcs_exceptions.TooManyRequests,
    gcs_exceptions.InternalServerError,
    gcs_exceptions.GatewayTimeout,
    ConnectionError,
)

_gcs_retry = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=30),
    retry=retry_if_exception_type(_TRANSIENT_GCS_EXCEPTIONS),
    reraise=True,
)


class GCSSync:
    """Upload/download files via GCS Object API with ETag caching.

    Designed for cross-service data sharing in IDEA Helsinki:
    - fcd-manager uploads segments.db
    - traffic-monitor uploads disturbances.db, downloads segments.db
    - orchestrator downloads segments.db and disturbances.db

    For testing with fake-gcs-server, set the ``STORAGE_EMULATOR_HOST``
    environment variable (e.g. ``http://localhost:4443``) before constructing
    the client.  The google-cloud-storage SDK routes all requests — metadata
    **and** media — through that endpoint automatically.

    Args:
        bucket_name: GCS bucket name.
        prefix: Key prefix for all objects (e.g. "idea-helsinki/").
            Normalized to ensure a trailing slash.
        credentials: Optional explicit credentials. Defaults to Application
            Default Credentials (automatic on GKE with Workload Identity).

    """

    def __init__(
        self,
        bucket_name: str,
        prefix: str = "",
        credentials: Credentials | None = None,
    ) -> None:
        self._client = storage.Client(credentials=credentials)
        self._bucket = self._client.bucket(bucket_name)

        try:
            if not self._bucket.exists():
                logger.info("Bucket %s does not exist. Creating it...", bucket_name)
                self._bucket.create()
        except (gcs_exceptions.Forbidden, gcs_exceptions.Conflict):
            # Expected in production (lack of bucket-level permissions) or race conditions.
            pass
        except Exception as e:
            logger.warning("Unexpected error checking/creating bucket %s: %s", bucket_name, e)

        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._etag_cache: dict[str, str] = {}
        logger.info(
            "GCSSync initialized: bucket=%s prefix=%s",
            bucket_name,
            self._prefix,
        )

    @staticmethod
    def _normalize_etag(etag: str | None) -> str:
        """Strip surrounding quotes from ETags for consistent comparison.

        The GCS SDK returns ETags with or without quotes depending on the
        operation (reload vs download_to_filename), so we normalize to bare
        values for reliable cache hits.
        """
        if etag is None:
            return ""
        return etag.strip('"')

    def _full_key(self, remote_key: str) -> str:
        return f"{self._prefix}{remote_key}"

    @_gcs_retry
    def upload(self, local_path: str | Path, remote_key: str) -> bool:
        """Upload a local file to GCS.

        Returns True on success, False on permanent errors.
        Transient errors are retried automatically.
        """
        full_key = self._full_key(remote_key)
        try:
            blob = self._bucket.blob(full_key)
            blob.upload_from_filename(str(local_path))
            self._etag_cache[remote_key] = self._normalize_etag(blob.etag)
            logger.info(
                "Uploaded %s → gs://%s/%s",
                local_path,
                self._bucket.name,
                full_key,
            )
            return True
        except _TRANSIENT_GCS_EXCEPTIONS:
            raise
        except Exception:
            logger.exception("Failed to upload %s to %s", local_path, full_key)
            return False

    @_gcs_retry
    def download_if_changed(self, remote_key: str, local_path: str | Path) -> bool:
        """Download a file from GCS only if it has changed since the last download.

        Uses ETag comparison to skip redundant downloads.

        Returns True if a new version was downloaded, False if unchanged,
        not found, or on permanent errors.
        """
        full_key = self._full_key(remote_key)
        try:
            blob = self._bucket.blob(full_key)
            blob.reload()
        except gcs_exceptions.NotFound:
            logger.warning("Object not found: gs://%s/%s", self._bucket.name, full_key)
            return False
        except _TRANSIENT_GCS_EXCEPTIONS:
            raise
        except Exception:
            logger.exception("Failed to check metadata for %s", full_key)
            return False

        cached_etag = self._etag_cache.get(remote_key)
        current_etag = self._normalize_etag(blob.etag)
        if cached_etag == current_etag:
            logger.debug(
                "No change for %s (ETag: %s), skipping download",
                remote_key,
                cached_etag,
            )
            return False

        try:
            local = Path(local_path)
            local.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local))
            self._etag_cache[remote_key] = self._normalize_etag(blob.etag)
            logger.info(
                "Downloaded gs://%s/%s → %s (ETag: %s)",
                self._bucket.name,
                full_key,
                local_path,
                blob.etag,
            )
            return True
        except _TRANSIENT_GCS_EXCEPTIONS:
            raise
        except Exception:
            logger.exception("Failed to download %s to %s", full_key, local_path)
            return False

    @property
    def etag_cache(self) -> dict[str, str]:
        """Read-only copy of the ETag cache for testing."""
        return dict(self._etag_cache)

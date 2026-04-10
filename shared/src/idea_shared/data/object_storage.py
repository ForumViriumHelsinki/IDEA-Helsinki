"""Object storage abstraction for cross-service data sharing.

Provides a backend-agnostic :class:`ObjectStorageSync` Protocol and a
:func:`create_object_storage_sync` factory for uploading/downloading files
between services.  The backend is selected via the ``OBJECT_STORAGE_BACKEND``
environment variable (default: ``"gcs"``).

Supported backends
------------------
- ``gcs`` *(default)*: Google Cloud Storage — see :class:`GCSSync`
- ``local``: Local filesystem — useful for development and testing

Future backends (not yet implemented)
--------------------------------------
- ``s3``: AWS S3
- ``azure``: Azure Blob Storage

Example
-------
::

    from idea_shared.data.object_storage import create_object_storage_sync

    # Resolved from OBJECT_STORAGE_BACKEND env var (defaults to "gcs")
    storage = create_object_storage_sync()
    storage.upload("/tmp/segments.db", "segments.db")
    storage.download_if_changed("segments.db", "/app/data/segments.db")

    # Explicit backend override
    storage = create_object_storage_sync(backend="local", base_dir="/tmp/store")
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ObjectStorageSync(Protocol):
    """Protocol for object storage sync backends.

    Any class that exposes compatible ``upload`` and ``download_if_changed``
    methods satisfies this protocol structurally — no explicit inheritance
    required.

    This enables swapping storage backends (GCS, S3, Azure Blob, local
    filesystem) without changing call-site code.

    Implementations
    ---------------
    - :class:`~idea_shared.data.gcs_sync.GCSSync` — Google Cloud Storage
    - :class:`LocalStorageSync` — local filesystem (development / testing)
    """

    def upload(self, local_path: str | Path, remote_key: str) -> bool:
        """Upload a local file to remote storage.

        Returns:
            ``True`` on success, ``False`` on permanent errors.
            Transient errors should be retried automatically by the
            implementation.
        """
        ...

    def download_if_changed(self, remote_key: str, local_path: str | Path) -> bool:
        """Download a remote file only if it has changed since last download.

        Uses change-detection (e.g. ETag, content hash, mtime) to skip
        redundant downloads.

        Returns:
            ``True`` if a new version was downloaded, ``False`` if unchanged,
            not found, or on permanent errors.
        """
        ...


class LocalStorageSync:
    """Local filesystem storage backend for development and testing.

    Treats a local directory as the "remote" store.  Files are identified by
    their ``remote_key``, stored under *base_dir*.

    Change detection is performed via SHA-256 content hash to mimic ETag-based
    skip logic from cloud backends.

    Args:
        base_dir: Base directory for stored objects.  Created if missing.
        prefix: Optional key prefix for all objects (mirrors :class:`GCSSync`
            API).  Normalised to include a trailing slash.
    """

    def __init__(self, base_dir: str | Path, prefix: str = "") -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._hash_cache: dict[str, str] = {}
        logger.info(
            "LocalStorageSync initialized: base_dir=%s prefix=%r",
            self._base_dir,
            self._prefix,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _full_path(self, remote_key: str) -> Path:
        return self._base_dir / f"{self._prefix}{remote_key}"

    @staticmethod
    def _file_hash(path: Path) -> str:
        """Return the SHA-256 hex digest of *path*."""
        import hashlib

        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65_536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Public API — matches ObjectStorageSync protocol
    # ------------------------------------------------------------------

    def upload(self, local_path: str | Path, remote_key: str) -> bool:
        """Copy *local_path* into the local storage directory.

        Returns:
            ``True`` on success, ``False`` if the copy fails.
        """
        src = Path(local_path)
        dest = self._full_path(remote_key)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            self._hash_cache[remote_key] = self._file_hash(dest)
            logger.info("LocalStorageSync: copied %s → %s", src, dest)
            return True
        except Exception:
            logger.exception(
                "LocalStorageSync: failed to copy %s → %s", src, dest
            )
            return False

    def download_if_changed(self, remote_key: str, local_path: str | Path) -> bool:
        """Copy from the local storage directory to *local_path* if changed.

        Returns:
            ``True`` if the file was copied (new or updated), ``False`` if
            unchanged or not found.
        """
        src = self._full_path(remote_key)
        dest = Path(local_path)

        if not src.exists():
            logger.warning("LocalStorageSync: object not found: %s", src)
            return False

        current_hash = self._file_hash(src)
        if self._hash_cache.get(remote_key) == current_hash:
            logger.debug(
                "LocalStorageSync: no change for %s (hash: %s), skipping",
                remote_key,
                current_hash,
            )
            return False

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            self._hash_cache[remote_key] = current_hash
            logger.info("LocalStorageSync: downloaded %s → %s", src, dest)
            return True
        except Exception:
            logger.exception(
                "LocalStorageSync: failed to download %s → %s", src, dest
            )
            return False

    @property
    def hash_cache(self) -> dict[str, str]:
        """Read-only copy of the content-hash cache (for testing)."""
        return dict(self._hash_cache)


def create_object_storage_sync(
    backend: str | None = None,
    bucket_name: str | None = None,
    prefix: str | None = None,
    **kwargs,
) -> ObjectStorageSync:
    """Create an object storage sync instance for the configured backend.

    Backend resolution order
    ------------------------
    1. *backend* argument (if provided)
    2. ``OBJECT_STORAGE_BACKEND`` environment variable
    3. Hard-coded default: ``"gcs"``

    Args:
        backend: Backend identifier.  Recognised values: ``"gcs"``,
            ``"local"``.  Values ``"s3"`` and ``"azure"`` are reserved and
            raise :exc:`NotImplementedError`.
        bucket_name: GCS bucket name (GCS backend only).  Defaults to the
            ``GCS_BUCKET_NAME`` constant (``GCS_BUCKET_NAME`` env var or
            ``"idea-helsinki-dev"``).
        prefix: Key prefix applied to all remote keys.  Defaults to
            ``GCS_PREFIX`` for GCS or ``""`` for local.
        **kwargs:
            - ``credentials`` (:class:`google.auth.credentials.Credentials`):
              explicit credentials for the GCS backend.  Defaults to
              Application Default Credentials.
            - ``base_dir`` (str | Path): base directory for the ``"local"``
              backend.  Defaults to ``<DATA_DIR>/local_storage``.

    Returns:
        An :class:`ObjectStorageSync`-compatible instance.

    Raises:
        NotImplementedError: If *backend* is ``"s3"`` or ``"azure"``
            (planned but not yet implemented).
        ValueError: If *backend* is not a recognised value.

    Examples:
        Using GCS (default when ``OBJECT_STORAGE_BACKEND`` is unset)::

            storage = create_object_storage_sync()

        Explicit local backend (no cloud credentials required)::

            storage = create_object_storage_sync(
                backend="local",
                base_dir="/tmp/test-storage",
            )

        Override via environment variable::

            # OBJECT_STORAGE_BACKEND=local
            storage = create_object_storage_sync()
    """
    from idea_shared.lib.Constants.Constants import (
        DATA_DIR,
        GCS_BUCKET_NAME,
        GCS_PREFIX,
        OBJECT_STORAGE_BACKEND,
    )

    resolved_backend = (backend or OBJECT_STORAGE_BACKEND).lower()

    if resolved_backend == "gcs":
        from idea_shared.data.gcs_sync import GCSSync

        return GCSSync(
            bucket_name=bucket_name or GCS_BUCKET_NAME,
            prefix=prefix if prefix is not None else GCS_PREFIX,
            credentials=kwargs.get("credentials"),
        )

    if resolved_backend == "local":
        base_dir = kwargs.get("base_dir", os.path.join(DATA_DIR, "local_storage"))
        return LocalStorageSync(
            base_dir=base_dir,
            prefix=prefix or "",
        )

    if resolved_backend in ("s3", "azure"):
        raise NotImplementedError(
            f"Storage backend {resolved_backend!r} is recognised but not yet "
            "implemented.  Contributions welcome — implement the "
            "ObjectStorageSync protocol and add a case to "
            "create_object_storage_sync()."
        )

    raise ValueError(
        f"Unknown storage backend: {resolved_backend!r}. "
        "Supported backends: 'gcs', 'local'."
    )

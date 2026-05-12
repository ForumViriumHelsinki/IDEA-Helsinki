"""Data access layer for IDEA Helsinki.

Provides repository abstractions for segment mapping, traffic disturbance,
and profile data. Backends (JSON, SQLite) implement the abstract interfaces.
GCSSync provides cross-service data sharing via GCS Object API.

Object storage backends are abstracted behind :class:`ObjectStorageSync` and
selected via :func:`create_object_storage_sync` (see ``object_storage`` module).
"""

from idea_shared.data.factory import create_repositories
from idea_shared.data.gcs_sync import GCSSync
from idea_shared.data.object_storage import (
    LocalStorageSync,
    ObjectStorageSync,
    create_object_storage_sync,
)
from idea_shared.data.repositories import (
    DisturbanceRepository,
    ProfileRepository,
    SegmentRepository,
)
from idea_shared.data.sqlite_backend import (
    SqliteDisturbanceRepository,
    SqliteIntegrityError,
    SqliteProfileRepository,
    SqliteSegmentRepository,
    create_sqlite_repositories,
)

__all__ = [
    "DisturbanceRepository",
    "GCSSync",
    "LocalStorageSync",
    "ObjectStorageSync",
    "ProfileRepository",
    "SegmentRepository",
    "SqliteDisturbanceRepository",
    "SqliteIntegrityError",
    "SqliteProfileRepository",
    "SqliteSegmentRepository",
    "create_object_storage_sync",
    "create_repositories",
    "create_sqlite_repositories",
]

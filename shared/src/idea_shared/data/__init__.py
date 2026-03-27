"""Data access layer for IDEA Helsinki.

Provides repository abstractions for segment mapping, traffic disturbance,
and profile data. Backends (JSON, SQLite) implement the abstract interfaces.
GCSSync provides cross-service data sharing via GCS Object API.
"""

from idea_shared.data.gcs_sync import GCSSync
from idea_shared.data.repositories import (
    DisturbanceRepository,
    ProfileRepository,
    SegmentRepository,
)
from idea_shared.data.sqlite_backend import (
    SqliteDisturbanceRepository,
    SqliteProfileRepository,
    SqliteSegmentRepository,
    create_sqlite_repositories,
)

__all__ = [
    "DisturbanceRepository",
    "GCSSync",
    "ProfileRepository",
    "SegmentRepository",
    "SqliteDisturbanceRepository",
    "SqliteProfileRepository",
    "SqliteSegmentRepository",
    "create_sqlite_repositories",
]

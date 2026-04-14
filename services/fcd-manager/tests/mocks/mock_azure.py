"""Mock Azure Blob Storage for testing."""

import random
from pathlib import Path


class MockBlob:
    """Mock blob object matching Azure SDK interface."""

    def __init__(self, name: str, content: bytes):
        """Initialize mock blob.

        Args:
            name: Blob name (includes timestamp pattern)
            content: Blob content bytes

        """
        self.name = name
        self._content = content


class MockAzureBlobStorage:
    """Mock Azure Blob Storage for deterministic testing.

    Features:
    - In-memory blob list with predefined content
    - Seeded shuffling for concurrency testing
    - Thread-safe operations
    """

    def __init__(self, fixture_dir: Path, seed: int | None = None):
        """Initialize mock Azure storage.

        Args:
            fixture_dir: Directory containing test fixture JSON files
            seed: Random seed for deterministic shuffling (None = no shuffle)

        """
        self.fixture_dir = fixture_dir
        self.seed = seed
        self._blobs: list[MockBlob] = []
        self._load_fixtures()

    def _load_fixtures(self):
        """Load all JSON fixture files as blobs."""
        json_files = sorted(self.fixture_dir.glob("blob_*.json"))
        for json_file in json_files:
            content = json_file.read_bytes()
            self._blobs.append(MockBlob(name=json_file.name, content=content))

    def get_blobs_in_range(self, start_time, end_time) -> list[MockBlob]:
        """Get blobs in time range, optionally shuffled.

        Args:
            start_time: Start datetime (ignored in mock)
            end_time: End datetime (ignored in mock)

        Returns:
            List of mock blobs, potentially shuffled

        """
        blobs = self._blobs.copy()

        if self.seed is not None:
            # Deterministic shuffling for concurrency testing
            random.seed(self.seed)
            random.shuffle(blobs)

        return blobs

    def download_blob_content(self, blob_name: str) -> bytes | None:
        """Download blob content by name.

        Args:
            blob_name: Blob name string

        Returns:
            Blob content bytes

        """
        # Find blob by name
        for blob in self._blobs:
            if blob.name == blob_name:
                return blob._content

        # Blob not found
        return None

    def reset(self):
        """Reset to initial state (reload fixtures)."""
        self._blobs.clear()
        self._load_fixtures()

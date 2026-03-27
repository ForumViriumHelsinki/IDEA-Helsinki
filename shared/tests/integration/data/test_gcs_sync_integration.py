"""Integration tests for GCSSync against fake-gcs-server."""

from __future__ import annotations

import pytest
from google.auth.credentials import AnonymousCredentials

from idea_shared.data.gcs_sync import GCSSync


def _make_sync(bucket_name: str, prefix: str) -> GCSSync:
    """Create a GCSSync using STORAGE_EMULATOR_HOST (set by fixture)."""
    return GCSSync(
        bucket_name=bucket_name,
        prefix=prefix,
        credentials=AnonymousCredentials(),
    )


@pytest.mark.integration
class TestGCSSyncIntegration:
    @pytest.fixture
    def uploader(self, gcs_bucket):
        """GCSSync instance for uploading (simulates writer service)."""
        return _make_sync(gcs_bucket, "test-prefix")

    @pytest.fixture
    def downloader(self, gcs_bucket):
        """Separate GCSSync instance for downloading (simulates reader service)."""
        return _make_sync(gcs_bucket, "test-prefix")

    def test_upload_and_download_roundtrip(self, uploader, downloader, tmp_path):
        src = tmp_path / "upload.db"
        src.write_bytes(b"hello world")
        dest = tmp_path / "download.db"

        assert uploader.upload(src, "round.db") is True
        assert downloader.download_if_changed("round.db", dest) is True
        assert dest.read_bytes() == b"hello world"

    def test_download_skips_unchanged(self, uploader, downloader, tmp_path):
        src = tmp_path / "upload.db"
        src.write_bytes(b"data")
        dest = tmp_path / "download.db"

        uploader.upload(src, "skip.db")
        assert downloader.download_if_changed("skip.db", dest) is True
        # Second download should skip — ETag now cached in downloader
        assert downloader.download_if_changed("skip.db", dest) is False

    def test_download_after_update(self, uploader, downloader, tmp_path):
        src = tmp_path / "upload.db"
        dest = tmp_path / "download.db"

        src.write_bytes(b"v1")
        uploader.upload(src, "update.db")
        downloader.download_if_changed("update.db", dest)
        assert dest.read_bytes() == b"v1"

        src.write_bytes(b"v2")
        uploader.upload(src, "update.db")
        assert downloader.download_if_changed("update.db", dest) is True
        assert dest.read_bytes() == b"v2"

    def test_download_missing_object(self, downloader, tmp_path):
        dest = tmp_path / "nope.db"
        assert downloader.download_if_changed("nonexistent.db", dest) is False
        assert not dest.exists()

    def test_independent_etags_per_key(self, uploader, downloader, tmp_path):
        f1 = tmp_path / "a.db"
        f1.write_bytes(b"aaa")
        f2 = tmp_path / "b.db"
        f2.write_bytes(b"bbb")

        uploader.upload(f1, "key-a.db")
        uploader.upload(f2, "key-b.db")

        dest = tmp_path / "out.db"

        # Download both
        assert downloader.download_if_changed("key-a.db", dest) is True
        assert downloader.download_if_changed("key-b.db", dest) is True

        # Second download of each should skip
        assert downloader.download_if_changed("key-a.db", dest) is False
        assert downloader.download_if_changed("key-b.db", dest) is False

    def test_prefix_isolation(self, gcs_bucket, tmp_path):
        sync_a = _make_sync(gcs_bucket, "ns-a")
        sync_b = _make_sync(gcs_bucket, "ns-b")

        src = tmp_path / "upload.db"
        src.write_bytes(b"from-a")
        sync_a.upload(src, "shared.db")

        dest = tmp_path / "download.db"
        # sync_b should not find sync_a's object under its prefix
        assert sync_b.download_if_changed("shared.db", dest) is False

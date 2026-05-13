"""Unit tests for GCSSync with mocked GCS client."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcs_exceptions

from idea_shared.data.gcs_sync import GCSSync


@pytest.fixture
def mock_gcs():
    """Mock GCS storage client, bucket, and blob."""
    with patch("idea_shared.data.gcs_sync.storage.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_bucket = MagicMock()
        mock_bucket.name = "test-bucket"
        mock_client.bucket.return_value = mock_bucket

        mock_blob = MagicMock()
        mock_blob.etag = "etag-abc-123"
        mock_bucket.blob.return_value = mock_blob

        yield {
            "client_cls": mock_cls,
            "client": mock_client,
            "bucket": mock_bucket,
            "blob": mock_blob,
        }


@pytest.fixture
def sync(mock_gcs):
    """Create a GCSSync instance with mocked client."""
    return GCSSync(bucket_name="test-bucket", prefix="data")


@pytest.mark.unit
class TestGCSSyncInit:
    def test_credentials_passed_to_client(self, mock_gcs):
        creds = MagicMock()
        GCSSync(bucket_name="b", credentials=creds)
        mock_gcs["client_cls"].assert_called_once_with(credentials=creds)

    def test_default_credentials_none(self, mock_gcs):
        GCSSync(bucket_name="b")
        mock_gcs["client_cls"].assert_called_once_with(credentials=None)

    def test_prefix_normalization_trailing_slash(self, mock_gcs):
        s = GCSSync(bucket_name="b", prefix="data/")
        assert s._prefix == "data/"

    def test_prefix_normalization_no_slash(self, mock_gcs):
        s = GCSSync(bucket_name="b", prefix="data")
        assert s._prefix == "data/"

    def test_empty_prefix(self, mock_gcs):
        s = GCSSync(bucket_name="b", prefix="")
        assert s._prefix == ""

    def test_no_prefix(self, mock_gcs):
        s = GCSSync(bucket_name="b")
        assert s._prefix == ""


@pytest.mark.unit
class TestUpload:
    def test_upload_success(self, sync, mock_gcs, tmp_path):
        f = tmp_path / "test.db"
        f.write_text("data")

        result = sync.upload(f, "segments.db")

        assert result is True
        mock_gcs["bucket"].blob.assert_called_with("data/segments.db")
        mock_gcs["blob"].upload_from_filename.assert_called_once_with(str(f))

    def test_upload_updates_etag_cache(self, sync, mock_gcs, tmp_path):
        f = tmp_path / "test.db"
        f.write_text("data")

        sync.upload(f, "segments.db")

        assert sync.etag_cache["segments.db"] == "etag-abc-123"

    def test_upload_returns_false_on_permission_error(self, sync, mock_gcs, tmp_path):
        f = tmp_path / "test.db"
        f.write_text("data")
        mock_gcs["blob"].upload_from_filename.side_effect = gcs_exceptions.Forbidden(
            "nope"
        )

        result = sync.upload(f, "segments.db")

        assert result is False
        assert "segments.db" not in sync.etag_cache

    @patch("time.sleep")
    def test_upload_retries_on_transient_error(
        self, mock_sleep, sync, mock_gcs, tmp_path
    ):
        f = tmp_path / "test.db"
        f.write_text("data")
        mock_gcs["blob"].upload_from_filename.side_effect = [
            gcs_exceptions.ServiceUnavailable("503"),
            None,
        ]

        result = sync.upload(f, "segments.db")

        assert result is True
        assert mock_gcs["blob"].upload_from_filename.call_count == 2

    def test_prefix_applied_to_key(self, sync, mock_gcs, tmp_path):
        f = tmp_path / "test.db"
        f.write_text("data")

        sync.upload(f, "sub/file.db")

        mock_gcs["bucket"].blob.assert_called_with("data/sub/file.db")

    def test_no_prefix_key(self, mock_gcs, tmp_path):
        s = GCSSync(bucket_name="b", prefix="")
        f = tmp_path / "test.db"
        f.write_text("data")

        s.upload(f, "file.db")

        mock_gcs["bucket"].blob.assert_called_with("file.db")


@pytest.mark.unit
class TestDownloadIfChanged:
    def test_downloads_when_no_cached_etag(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"

        result = sync.download_if_changed("segments.db", dest)

        assert result is True
        mock_gcs["blob"].reload.assert_called_once()
        mock_gcs["blob"].download_to_filename.assert_called_once_with(str(dest))

    def test_skips_when_etag_matches(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"
        sync._etag_cache["segments.db"] = "etag-abc-123"

        result = sync.download_if_changed("segments.db", dest)

        assert result is False
        mock_gcs["blob"].download_to_filename.assert_not_called()

    def test_downloads_when_etag_differs(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"
        sync._etag_cache["segments.db"] = "old-etag"

        result = sync.download_if_changed("segments.db", dest)

        assert result is True
        mock_gcs["blob"].download_to_filename.assert_called_once()

    def test_updates_etag_cache_after_download(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"

        sync.download_if_changed("segments.db", dest)

        assert sync.etag_cache["segments.db"] == "etag-abc-123"

    def test_returns_false_on_not_found(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"
        mock_gcs["blob"].reload.side_effect = gcs_exceptions.NotFound("404")

        result = sync.download_if_changed("segments.db", dest)

        assert result is False
        mock_gcs["blob"].download_to_filename.assert_not_called()

    @patch("time.sleep")
    def test_retries_on_transient_error(self, mock_sleep, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"
        mock_gcs["blob"].reload.side_effect = [
            gcs_exceptions.ServiceUnavailable("503"),
            None,
        ]

        result = sync.download_if_changed("segments.db", dest)

        assert result is True
        assert mock_gcs["blob"].reload.call_count == 2

    def test_creates_parent_directory(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "nested" / "deep" / "out.db"

        sync.download_if_changed("segments.db", dest)

        assert dest.parent.exists()

    def test_prefix_applied_to_key(self, sync, mock_gcs, tmp_path):
        dest = tmp_path / "out.db"

        sync.download_if_changed("segments.db", dest)

        mock_gcs["bucket"].blob.assert_called_with("data/segments.db")


@pytest.mark.unit
class TestEtagCache:
    def test_etag_cache_returns_copy(self, sync):
        sync._etag_cache["key"] = "value"
        cache = sync.etag_cache
        cache["key"] = "modified"
        assert sync._etag_cache["key"] == "value"

    def test_etag_cache_empty_initially(self, sync):
        assert sync.etag_cache == {}

    def test_invalidate_cache_drops_entry(self, sync):
        """invalidate_cache lets callers re-download after a corrupt local copy.

        Regression for issue #459: the orchestrator deletes the local SQLite
        file and asks GCSSync to forget the cached ETag so the next refresh
        re-downloads instead of skipping on ETag equality.
        """
        sync._etag_cache["disturbances.db"] = "etag-old"
        sync.invalidate_cache("disturbances.db")
        assert "disturbances.db" not in sync._etag_cache

    def test_invalidate_unknown_key_is_noop(self, sync):
        """Invalidating an unseen key is allowed (no KeyError)."""
        sync.invalidate_cache("never-seen.db")

"""Unit tests for ObjectStorageSync protocol, LocalStorageSync, and factory."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from idea_shared.data.object_storage import (
    LocalStorageSync,
    ObjectStorageSync,
    create_object_storage_sync,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MinimalSync:
    """Minimal class that satisfies the ObjectStorageSync protocol."""

    def upload(self, local_path, remote_key):
        return True

    def download_if_changed(self, remote_key, local_path):
        return False


class _IncompatibleSync:
    """Class that does NOT satisfy the protocol (missing download_if_changed)."""

    def upload(self, local_path, remote_key):
        return True


# ---------------------------------------------------------------------------
# Protocol structural typing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestObjectStorageSyncProtocol:
    def test_gcs_sync_satisfies_protocol(self):
        """GCSSync should satisfy the protocol without explicit inheritance."""
        from unittest.mock import MagicMock, patch

        with patch("idea_shared.data.gcs_sync.storage.Client"):
            from idea_shared.data.gcs_sync import GCSSync

            instance = GCSSync.__new__(GCSSync)
            instance._client = MagicMock()
            instance._bucket = MagicMock()
            instance._prefix = ""
            instance._etag_cache = {}
            assert isinstance(instance, ObjectStorageSync)

    def test_local_storage_sync_satisfies_protocol(self, tmp_path):
        instance = LocalStorageSync(base_dir=tmp_path)
        assert isinstance(instance, ObjectStorageSync)

    def test_minimal_class_satisfies_protocol(self):
        assert isinstance(_MinimalSync(), ObjectStorageSync)

    def test_missing_method_fails_protocol_check(self):
        assert not isinstance(_IncompatibleSync(), ObjectStorageSync)


# ---------------------------------------------------------------------------
# LocalStorageSync
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    """A LocalStorageSync instance with a temp base directory."""
    return LocalStorageSync(base_dir=tmp_path / "store", prefix="data")


@pytest.mark.unit
class TestLocalStorageSyncInit:
    def test_creates_base_dir(self, tmp_path):
        base = tmp_path / "new_dir"
        assert not base.exists()
        LocalStorageSync(base_dir=base)
        assert base.is_dir()

    def test_prefix_normalization_trailing_slash(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path, prefix="data/")
        assert s._prefix == "data/"

    def test_prefix_normalization_no_slash(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path, prefix="data")
        assert s._prefix == "data/"

    def test_empty_prefix(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path, prefix="")
        assert s._prefix == ""

    def test_no_prefix(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path)
        assert s._prefix == ""

    def test_hash_cache_empty_initially(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path)
        assert s.hash_cache == {}


@pytest.mark.unit
class TestLocalStorageSyncUpload:
    def test_upload_creates_file(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"hello")

        result = store.upload(src, "segments.db")

        assert result is True
        dest = store._full_path("segments.db")
        assert dest.exists()
        assert dest.read_bytes() == b"hello"

    def test_upload_does_not_update_hash_cache(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"hello")

        store.upload(src, "segments.db")

        # upload() intentionally does not populate the download-tracking cache;
        # only download_if_changed() updates it after a successful fetch.
        assert "segments.db" not in store.hash_cache

    def test_upload_applies_prefix(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"data")
        store.upload(src, "sub.db")
        assert (store._base_dir / "data" / "sub.db").exists()

    def test_upload_no_prefix(self, tmp_path):
        s = LocalStorageSync(base_dir=tmp_path / "store")
        src = tmp_path / "file.db"
        src.write_bytes(b"x")
        s.upload(src, "file.db")
        assert (s._base_dir / "file.db").exists()

    def test_upload_returns_false_on_error(self, store, tmp_path):
        non_existent = tmp_path / "does_not_exist.db"
        result = store.upload(non_existent, "target.db")
        assert result is False

    def test_upload_creates_parent_directories(self, store, tmp_path):
        src = tmp_path / "file.db"
        src.write_bytes(b"x")
        result = store.upload(src, "nested/deep/file.db")
        assert result is True
        assert (store._base_dir / "data" / "nested" / "deep" / "file.db").exists()

    def test_upload_accepts_string_path(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"str path")
        result = store.upload(str(src), "segments.db")
        assert result is True


@pytest.mark.unit
class TestLocalStorageSyncDownload:
    def test_downloads_when_no_cached_hash(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"content")
        store.upload(src, "segments.db")

        # Create a fresh store (no hash cache) to simulate a new service instance
        fresh_store = LocalStorageSync(base_dir=store._base_dir, prefix="data")
        dest = tmp_path / "dest.db"
        result = fresh_store.download_if_changed("segments.db", dest)

        assert result is True
        assert dest.read_bytes() == b"content"

    def test_skips_when_hash_matches(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"content")
        store.upload(src, "segments.db")

        dest = tmp_path / "dest.db"
        store.download_if_changed(
            "segments.db", dest
        )  # First download, populates cache

        # Second call: hash is cached, should skip
        result = store.download_if_changed("segments.db", dest)
        assert result is False

    def test_downloads_when_content_changed(self, store, tmp_path):
        src = tmp_path / "source.db"
        dest = tmp_path / "dest.db"

        src.write_bytes(b"v1")
        store.upload(src, "segments.db")
        store.download_if_changed("segments.db", dest)
        assert dest.read_bytes() == b"v1"

        # Update source and re-upload
        src.write_bytes(b"v2")
        store.upload(src, "segments.db")

        result = store.download_if_changed("segments.db", dest)
        assert result is True
        assert dest.read_bytes() == b"v2"

    def test_returns_false_when_not_found(self, store, tmp_path):
        dest = tmp_path / "dest.db"
        result = store.download_if_changed("nonexistent.db", dest)
        assert result is False
        assert not dest.exists()

    def test_updates_hash_cache_after_download(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"data")
        store.upload(src, "segments.db")

        fresh_store = LocalStorageSync(base_dir=store._base_dir, prefix="data")
        dest = tmp_path / "dest.db"
        fresh_store.download_if_changed("segments.db", dest)

        assert "segments.db" in fresh_store.hash_cache

    def test_creates_parent_directories(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"x")
        store.upload(src, "segments.db")

        dest = tmp_path / "nested" / "deep" / "dest.db"
        result = store.download_if_changed("segments.db", dest)
        assert result is True
        assert dest.parent.exists()

    def test_accepts_string_path(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"x")
        store.upload(src, "segments.db")

        fresh = LocalStorageSync(base_dir=store._base_dir, prefix="data")
        dest = tmp_path / "dest.db"
        result = fresh.download_if_changed("segments.db", str(dest))
        assert result is True

    def test_returns_false_when_src_is_directory(self, store, tmp_path):
        # Create a directory at the resolved remote path; should not crash.
        src_dir = store._full_path("adir")
        src_dir.mkdir(parents=True, exist_ok=True)
        dest = tmp_path / "dest.db"
        result = store.download_if_changed("adir", dest)
        assert result is False
        assert not dest.exists()

    def test_redownloads_when_dest_deleted(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"content")
        store.upload(src, "segments.db")

        dest = tmp_path / "dest.db"
        assert store.download_if_changed("segments.db", dest) is True

        # External deletion of dest should trigger a fresh download even
        # though the hash cache still has a matching entry.
        dest.unlink()
        result = store.download_if_changed("segments.db", dest)
        assert result is True
        assert dest.read_bytes() == b"content"

    def test_leading_slash_in_remote_key(self, store, tmp_path):
        src = tmp_path / "source.db"
        src.write_bytes(b"x")
        store.upload(src, "segments.db")

        # Leading slash on remote_key should resolve to the same object.
        dest = tmp_path / "dest.db"
        result = store.download_if_changed("/segments.db", dest)
        assert result is True
        assert dest.read_bytes() == b"x"


@pytest.mark.unit
class TestLocalStorageSyncHashCache:
    def test_hash_cache_returns_copy(self, tmp_path):
        # Use a dedicated store dir so src != dest (avoids SameFileError).
        s = LocalStorageSync(base_dir=tmp_path / "store")
        src = tmp_path / "f.db"
        src.write_bytes(b"x")
        s.upload(src, "f.db")
        # download_if_changed populates the hash cache (upload does not).
        dest = tmp_path / "dest.db"
        s.download_if_changed("f.db", dest)
        cache = s.hash_cache
        cache["f.db"] = "tampered"
        assert s._hash_cache["f.db"] != "tampered"


# ---------------------------------------------------------------------------
# create_object_storage_sync factory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateObjectStorageSync:
    def test_defaults_to_gcs_backend(self, tmp_path):
        """When OBJECT_STORAGE_BACKEND is unset (or "gcs"), returns GCSSync."""
        with (
            patch.dict(os.environ, {"OBJECT_STORAGE_BACKEND": "gcs"}, clear=False),
            patch("idea_shared.data.gcs_sync.storage.Client"),
        ):
            result = create_object_storage_sync()
            from idea_shared.data.gcs_sync import GCSSync

            assert isinstance(result, GCSSync)

    def test_gcs_backend_explicit(self, tmp_path):
        with patch("idea_shared.data.gcs_sync.storage.Client"):
            result = create_object_storage_sync(backend="gcs")
            from idea_shared.data.gcs_sync import GCSSync

            assert isinstance(result, GCSSync)

    def test_local_backend_explicit(self, tmp_path):
        result = create_object_storage_sync(
            backend="local", base_dir=str(tmp_path / "store")
        )
        assert isinstance(result, LocalStorageSync)

    def test_local_backend_via_constant(self, tmp_path):
        """Backend selection via the OBJECT_STORAGE_BACKEND constant (env var path)."""
        with patch(
            "idea_shared.lib.Constants.Constants.OBJECT_STORAGE_BACKEND",
            "local",
        ):
            result = create_object_storage_sync(
                base_dir=str(tmp_path / "store"),
            )
            assert isinstance(result, LocalStorageSync)

    def test_backend_argument_overrides_env(self, tmp_path):
        """Explicit backend= kwarg wins over env var."""
        with patch.dict(os.environ, {"OBJECT_STORAGE_BACKEND": "gcs"}, clear=False):
            result = create_object_storage_sync(
                backend="local",
                base_dir=str(tmp_path / "store"),
            )
            assert isinstance(result, LocalStorageSync)

    def test_s3_backend_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="s3"):
            create_object_storage_sync(backend="s3")

    def test_azure_backend_raises_not_implemented(self):
        with pytest.raises(NotImplementedError, match="azure"):
            create_object_storage_sync(backend="azure")

    def test_unknown_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown storage backend"):
            create_object_storage_sync(backend="minio")

    def test_backend_is_case_insensitive(self, tmp_path):
        result = create_object_storage_sync(
            backend="LOCAL", base_dir=str(tmp_path / "store")
        )
        assert isinstance(result, LocalStorageSync)

    def test_local_backend_custom_base_dir(self, tmp_path):
        custom_dir = tmp_path / "custom"
        result = create_object_storage_sync(backend="local", base_dir=str(custom_dir))
        assert isinstance(result, LocalStorageSync)
        assert result._base_dir == custom_dir

    def test_gcs_backend_passes_custom_bucket_name(self):
        with patch("idea_shared.data.gcs_sync.storage.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            create_object_storage_sync(backend="gcs", bucket_name="my-custom-bucket")
            mock_client.bucket.assert_called_once_with("my-custom-bucket")

    def test_gcs_backend_passes_custom_prefix(self):
        with patch("idea_shared.data.gcs_sync.storage.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            result = create_object_storage_sync(backend="gcs", prefix="custom/prefix")
            from idea_shared.data.gcs_sync import GCSSync

            assert isinstance(result, GCSSync)
            assert result._prefix == "custom/prefix/"

    def test_gcs_backend_passes_credentials(self):
        creds = MagicMock()
        with patch("idea_shared.data.gcs_sync.storage.Client") as mock_cls:
            mock_cls.return_value = MagicMock()
            create_object_storage_sync(backend="gcs", credentials=creds)
            mock_cls.assert_called_once_with(credentials=creds)

    def test_result_satisfies_protocol(self, tmp_path):
        result = create_object_storage_sync(
            backend="local", base_dir=str(tmp_path / "store")
        )
        assert isinstance(result, ObjectStorageSync)

"""Fixtures for GCS integration tests using fake-gcs-server."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time

import pytest
import requests
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.fixture(scope="session")
def fake_gcs_server():
    """Start a fake-gcs-server Docker container for integration tests.

    Sets STORAGE_EMULATOR_HOST so the google-cloud-storage SDK routes
    all requests (metadata and media) through the emulator.

    Uses -external-url to ensure media_link URLs in server responses
    point to localhost:<port> instead of the container's internal address.

    Yields the HTTP endpoint URL. Skips if Docker is unavailable.
    """
    if not _docker_available():
        pytest.skip("Docker not available")

    port = _find_free_port()
    container_name = f"fake-gcs-{port}"
    endpoint = f"http://localhost:{port}"

    # Use matching internal/external port and -external-url so all URLs
    # in server responses (including media_link) resolve correctly.
    proc = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{port}:{port}",
            "fsouza/fake-gcs-server:latest",
            "-scheme",
            "http",
            "-port",
            str(port),
            "-external-url",
            endpoint,
        ],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        pytest.skip(f"Failed to start fake-gcs-server: {proc.stderr}")

    # Wait for server to be ready
    for _ in range(30):
        try:
            resp = requests.get(f"{endpoint}/storage/v1/b", timeout=1)
            if resp.status_code in (200, 404):
                break
        except Exception:
            time.sleep(0.5)
    else:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
        pytest.skip("fake-gcs-server failed to start in time")

    old_env = os.environ.get("STORAGE_EMULATOR_HOST")
    os.environ["STORAGE_EMULATOR_HOST"] = endpoint

    yield endpoint

    if old_env is None:
        os.environ.pop("STORAGE_EMULATOR_HOST", None)
    else:
        os.environ["STORAGE_EMULATOR_HOST"] = old_env

    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.fixture
def gcs_bucket(fake_gcs_server):
    """Create a test bucket on fake-gcs-server and return bucket_name."""
    client = storage.Client(
        credentials=AnonymousCredentials(),
        project="test-project",
    )

    bucket_name = "test-bucket"
    try:
        client.create_bucket(bucket_name)
    except Exception:
        pass  # Bucket may already exist from a previous test

    return bucket_name

"""Sentry SDK initialization for IDEA-Helsinki services."""

import os
from pathlib import Path

import sentry_sdk

from idea_shared.classes.Logger import Logger

logger = Logger(__name__)

VERSION_FILE = Path("/app/VERSION")


def _detect_release() -> str | None:
    """Detect the release version from environment or VERSION file.

    Checks in order:
    1. SENTRY_RELEASE environment variable (explicit override)
    2. /app/VERSION file (written during Docker build)

    Returns:
        Release string or None if not determinable.
    """
    release = os.getenv("SENTRY_RELEASE", "").strip()
    if release:
        return release

    try:
        if VERSION_FILE.is_file():
            version = VERSION_FILE.read_text().strip()
            if version:
                return f"idea-helsinki@{version}"
    except OSError as e:
        logger.warning(f"Could not read version file at {VERSION_FILE}: {e}")

    return None


def configure_sentry(service_name: str) -> None:
    """Initialize Sentry SDK if SENTRY_DSN environment variable is set.

    Args:
        service_name: Name of the service for logging context.
    """
    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if sentry_dsn:
        release = _detect_release()
        sentry_sdk.init(
            dsn=sentry_dsn,
            release=release,
            sample_rate=0.1,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info(f"Sentry initialized for {service_name} (release={release})")
    else:
        logger.info("SENTRY_DSN not set, running without Sentry error tracking")

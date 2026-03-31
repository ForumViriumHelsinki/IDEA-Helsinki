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


def _get_sample_rate_from_env(env_var: str, default: float) -> float:
    """Parse a sampling rate from an environment variable.

    Validates that the value is a float in the range [0.0, 1.0].  Falls back
    to *default* and logs a warning for missing, non-numeric, or out-of-range
    values.

    Args:
        env_var: Name of the environment variable to read.
        default: Value to use when the env var is absent or invalid.

    Returns:
        Float between 0.0 and 1.0.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
        if 0.0 <= val <= 1.0:
            return val
        logger.warning(
            f"Invalid {env_var} value {val}: must be between 0.0 and 1.0. "
            f"Using default {default}"
        )
    except ValueError:
        logger.warning(
            f"Invalid {env_var} value '{raw}': not a float. Using default {default}"
        )
    return default


def _get_sample_rate() -> float:
    """Get error sample rate from environment or default to 1.0.

    Errors are infrequent and high-value; capture all of them by default.
    Override with SENTRY_SAMPLE_RATE environment variable (0.0–1.0).

    Returns:
        Float between 0.0 and 1.0.
    """
    return _get_sample_rate_from_env("SENTRY_SAMPLE_RATE", 1.0)


def _get_traces_sample_rate() -> float:
    """Get transaction traces sample rate from environment or default to 0.1.

    100% transaction tracing is aggressive for production; default to 10%.
    Override with SENTRY_TRACES_SAMPLE_RATE environment variable (0.0–1.0).

    Returns:
        Float between 0.0 and 1.0.
    """
    return _get_sample_rate_from_env("SENTRY_TRACES_SAMPLE_RATE", 0.1)


def _get_profiles_sample_rate() -> float:
    """Get profiling sample rate from environment or default to 0.1.

    Profiles are heavy; sample sparingly in production by default (10%).
    Override with SENTRY_PROFILES_SAMPLE_RATE environment variable (0.0–1.0).

    Returns:
        Float between 0.0 and 1.0.
    """
    return _get_sample_rate_from_env("SENTRY_PROFILES_SAMPLE_RATE", 0.1)


def configure_sentry(service_name: str) -> None:
    """Initialize Sentry SDK if SENTRY_DSN environment variable is set.

    Sampling rates are configurable via environment variables:
    - SENTRY_SAMPLE_RATE: Error sampling rate (default: 1.0 — capture all errors)
    - SENTRY_TRACES_SAMPLE_RATE: Transaction tracing rate (default: 0.1 — 10%)
    - SENTRY_PROFILES_SAMPLE_RATE: Profiling rate (default: 0.1 — 10%)

    Args:
        service_name: Name of the service for logging context.
    """
    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if sentry_dsn:
        release = _detect_release()
        sample_rate = _get_sample_rate()
        traces_sample_rate = _get_traces_sample_rate()
        profiles_sample_rate = _get_profiles_sample_rate()
        sentry_sdk.init(
            dsn=sentry_dsn,
            release=release,
            sample_rate=sample_rate,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        sentry_sdk.set_tag("service", service_name)
        logger.info(
            f"Sentry initialized for {service_name} (release={release}, "
            f"sample_rate={sample_rate}, traces_sample_rate={traces_sample_rate}, "
            f"profiles_sample_rate={profiles_sample_rate})"
        )
    else:
        logger.info("SENTRY_DSN not set, running without Sentry error tracking")

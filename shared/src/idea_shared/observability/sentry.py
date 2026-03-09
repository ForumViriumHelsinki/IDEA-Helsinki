"""Sentry SDK initialization for IDEA-Helsinki services."""

import os

import sentry_sdk

from idea_shared.classes.Logger import Logger

logger = Logger(__name__)


def configure_sentry(service_name: str) -> None:
    """Initialize Sentry SDK if SENTRY_DSN environment variable is set.

    Args:
        service_name: Name of the service for logging context.
    """
    sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            sample_rate=0.1,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
            environment=os.getenv("ENVIRONMENT", "production"),
        )
        logger.info(f"Sentry initialized for {service_name}")
    else:
        logger.info("SENTRY_DSN not set, running without Sentry error tracking")

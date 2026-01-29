"""Shared feature flag initialization helper.

This module provides a consistent way to initialize feature flags across
all IDEA-Helsinki services with automatic provider selection based on
environment configuration.

Provider selection order:
1. FEATURE_FLAG_ENDPOINT set -> GoFeatureFlagProvider (centralized relay proxy)
2. ENVIRONMENT=production -> EnvironmentVariableProvider (fallback)
3. Otherwise -> JsonFileProvider (local development)

Example:
    >>> from idea_shared.feature_flags.initialization import init_feature_flags
    >>>
    >>> # At service startup
    >>> init_feature_flags(data_dir="/app/data", service_name="fcd-manager")
"""

import logging
import os

from openfeature.provider import AbstractProvider

from .manager import initialize_feature_flags
from .providers import EnvironmentVariableProvider, JsonFileProvider

logger = logging.getLogger(__name__)


def create_provider(data_dir: str = "/app/data") -> AbstractProvider:
    """Create the appropriate feature flag provider based on environment.

    Provider selection logic:
    1. If FEATURE_FLAG_ENDPOINT is set, use GoFeatureFlagProvider
       (connects to centralized relay proxy)
    2. If ENVIRONMENT=production, use EnvironmentVariableProvider
       (fallback for production without relay proxy)
    3. Otherwise, use JsonFileProvider
       (local development with JSON config file)

    Args:
        data_dir: Directory containing feature_flags.json for local dev

    Returns:
        Configured feature flag provider
    """
    endpoint = os.getenv("FEATURE_FLAG_ENDPOINT")

    if endpoint:
        # Lazy import to avoid dependency issues when GOFF provider is not needed
        from .providers import GoFeatureFlagProvider

        timeout = int(os.getenv("FEATURE_FLAG_TIMEOUT", "3000"))
        logger.info(f"Using GoFeatureFlagProvider with endpoint: {endpoint}")
        return GoFeatureFlagProvider(endpoint=endpoint, timeout=timeout)

    environment = os.getenv("ENVIRONMENT", "development")
    if environment == "production":
        logger.info("Using EnvironmentVariableProvider for feature flags")
        return EnvironmentVariableProvider()

    feature_flags_path = os.path.join(data_dir, "feature_flags.json")
    logger.info(f"Using JsonFileProvider with path: {feature_flags_path}")
    return JsonFileProvider(feature_flags_path)


def init_feature_flags(
    data_dir: str = "/app/data",
    service_name: str = "idea-helsinki",
) -> bool:
    """Initialize feature flags with automatic provider selection.

    This is the recommended way to initialize feature flags in IDEA-Helsinki
    services. It handles provider selection, error recovery, and logging.

    Args:
        data_dir: Directory containing feature_flags.json for local dev
        service_name: Service name for logging

    Returns:
        True if initialization succeeded, False otherwise
    """
    try:
        provider = create_provider(data_dir)
        initialize_feature_flags(provider)

        provider_name = provider.get_metadata().name
        logger.info(
            f"Feature flags initialized for {service_name} using {provider_name}"
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to initialize feature flags for {service_name}: {e}")
        logger.warning("Continuing with default flag values")
        return False

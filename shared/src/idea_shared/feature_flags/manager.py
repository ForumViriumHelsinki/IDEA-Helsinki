"""Feature flag manager for IDEA Helsinki services.

This module provides a singleton wrapper around the OpenFeature API
for easy access to feature flags throughout the application.
"""

import logging
import threading
from typing import Any

from openfeature import api
from openfeature.client import OpenFeatureClient
from openfeature.evaluation_context import EvaluationContext
from openfeature.provider import AbstractProvider

from .flags import FlagDefaults, FeatureFlag

logger = logging.getLogger(__name__)


class FeatureFlagManager:
    """Feature flag manager using OpenFeature SDK.

    This class provides a convenient wrapper around the OpenFeature client
    with type-safe flag evaluation and default value handling.

    Example:
        >>> from idea_shared.feature_flags import FeatureFlagManager
        >>> from idea_shared.feature_flags.providers import JsonFileProvider
        >>>
        >>> provider = JsonFileProvider("feature_flags.json")
        >>> manager = FeatureFlagManager(provider)
        >>>
        >>> if manager.is_enabled(FeatureFlag.ENABLE_CACHING):
        ...     # Use caching
        ...     pass
    """

    def __init__(self, provider: AbstractProvider, domain: str = "idea-helsinki"):
        """Initialize the feature flag manager.

        Args:
            provider: OpenFeature provider for flag resolution
            domain: Client domain name (default: idea-helsinki)
        """
        self._provider = provider
        self._domain = domain

        # Set the provider for the domain
        api.set_provider(provider, domain=domain)

        # Get the client for this domain
        self._client: OpenFeatureClient = api.get_client(domain=domain)

        logger.info(
            f"Initialized FeatureFlagManager with provider: "
            f"{provider.get_metadata().name}"
        )

    def is_enabled(
        self,
        flag: FeatureFlag | str,
        default: bool | None = None,
        context: EvaluationContext | None = None,
    ) -> bool:
        """Check if a boolean feature flag is enabled.

        Args:
            flag: Feature flag to check
            default: Default value (uses FlagDefaults if None)
            context: Optional evaluation context

        Returns:
            True if flag is enabled, False otherwise
        """
        flag_key = flag.value if isinstance(flag, FeatureFlag) else flag

        if default is None:
            try:
                default = FlagDefaults.get_default(
                    FeatureFlag(flag_key) if isinstance(flag_key, str) else flag
                )
            except (AttributeError, ValueError):
                default = False
                logger.warning(
                    f"No default found for flag {flag_key}, using False as default"
                )

        return self._client.get_boolean_value(
            flag_key=flag_key,
            default_value=default,
            evaluation_context=context,
        )

    def get_string(
        self,
        flag: FeatureFlag | str,
        default: str,
        context: EvaluationContext | None = None,
    ) -> str:
        """Get a string feature flag value.

        Args:
            flag: Feature flag to get
            default: Default value if flag is not set
            context: Optional evaluation context

        Returns:
            Flag value or default
        """
        flag_key = flag.value if isinstance(flag, FeatureFlag) else flag

        return self._client.get_string_value(
            flag_key=flag_key,
            default_value=default,
            evaluation_context=context,
        )

    def get_int(
        self,
        flag: FeatureFlag | str,
        default: int,
        context: EvaluationContext | None = None,
    ) -> int:
        """Get an integer feature flag value.

        Args:
            flag: Feature flag to get
            default: Default value if flag is not set
            context: Optional evaluation context

        Returns:
            Flag value or default
        """
        flag_key = flag.value if isinstance(flag, FeatureFlag) else flag

        return self._client.get_integer_value(
            flag_key=flag_key,
            default_value=default,
            evaluation_context=context,
        )

    def get_float(
        self,
        flag: FeatureFlag | str,
        default: float,
        context: EvaluationContext | None = None,
    ) -> float:
        """Get a float feature flag value.

        Args:
            flag: Feature flag to get
            default: Default value if flag is not set
            context: Optional evaluation context

        Returns:
            Flag value or default
        """
        flag_key = flag.value if isinstance(flag, FeatureFlag) else flag

        return self._client.get_float_value(
            flag_key=flag_key,
            default_value=default,
            evaluation_context=context,
        )

    def get_object(
        self,
        flag: FeatureFlag | str,
        default: dict,
        context: EvaluationContext | None = None,
    ) -> dict:
        """Get a dict/object feature flag value.

        Args:
            flag: Feature flag to get
            default: Default value if flag is not set
            context: Optional evaluation context

        Returns:
            Flag value or default
        """
        flag_key = flag.value if isinstance(flag, FeatureFlag) else flag

        return self._client.get_object_value(
            flag_key=flag_key,
            default_value=default,
            evaluation_context=context,
        )

    def get_all_flags(self) -> dict[str, Any]:
        """Get all currently configured flags (if supported by provider).

        Returns:
            Dictionary of flag names to values (may be empty if not supported)
        """
        # This is a convenience method that could be extended
        # if providers support bulk flag retrieval
        logger.warning(
            "get_all_flags() returns empty dict - "
            "individual flag evaluation is recommended"
        )
        return {}


# Global singleton instance
_global_manager: FeatureFlagManager | None = None
_init_lock = threading.Lock()


def initialize_feature_flags(
    provider: AbstractProvider, domain: str = "idea-helsinki"
) -> FeatureFlagManager:
    """Initialize the global feature flag manager.

    This should be called once at application startup.
    Thread-safe: Multiple concurrent calls will block until initialization completes.

    Args:
        provider: OpenFeature provider for flag resolution
        domain: Client domain name (default: idea-helsinki)

    Returns:
        Initialized FeatureFlagManager instance

    Note:
        In async applications, ensure this is called during synchronous
        initialization (e.g., before starting the event loop) to avoid
        race conditions.
    """
    global _global_manager

    # Use double-checked locking pattern for performance
    if _global_manager is None:
        with _init_lock:
            # Check again inside lock to prevent race condition
            if _global_manager is None:
                _global_manager = FeatureFlagManager(provider, domain)
                logger.info("Global feature flag manager initialized")

    return _global_manager


def get_feature_flags() -> FeatureFlagManager:
    """Get the global feature flag manager instance.

    Returns:
        Global FeatureFlagManager instance

    Raises:
        RuntimeError: If feature flags haven't been initialized
    """
    if _global_manager is None:
        raise RuntimeError(
            "Feature flags not initialized. "
            "Call initialize_feature_flags() first at application startup."
        )
    return _global_manager

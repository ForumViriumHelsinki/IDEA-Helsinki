"""Feature flags support for IDEA Helsinki services.

This module provides OpenFeature-based feature flag management with
support for multiple providers (JSON files, environment variables, etc.).

Basic usage:
    >>> from idea_shared.feature_flags import (
    ...     initialize_feature_flags,
    ...     get_feature_flags,
    ...     FeatureFlag,
    ... )
    >>> from idea_shared.feature_flags.providers import JsonFileProvider
    >>>
    >>> # Initialize at startup
    >>> provider = JsonFileProvider("data/feature_flags.json")
    >>> initialize_feature_flags(provider)
    >>>
    >>> # Use throughout application
    >>> flags = get_feature_flags()
    >>> if flags.is_enabled(FeatureFlag.ENABLE_CACHING):
    ...     # Use caching
    ...     pass
"""

from .flags import FlagDefaults, FeatureFlag
from .manager import (
    FeatureFlagManager,
    get_feature_flags,
    initialize_feature_flags,
)
from .providers import EnvironmentVariableProvider, JsonFileProvider

__all__ = [
    # Core classes
    "FeatureFlagManager",
    # Singleton functions
    "initialize_feature_flags",
    "get_feature_flags",
    # Flag definitions
    "FeatureFlag",
    "FlagDefaults",
    # Providers
    "JsonFileProvider",
    "EnvironmentVariableProvider",
]

"""Feature flags support for IDEA Helsinki services.

This module provides OpenFeature-based feature flag management with
support for multiple providers (JSON files, environment variables,
GoFeatureFlag relay proxy, etc.).

Basic usage:
    >>> from idea_shared.feature_flags import (
    ...     init_feature_flags,
    ...     get_feature_flags,
    ...     FeatureFlag,
    ... )
    >>>
    >>> # Initialize at startup (automatic provider selection)
    >>> init_feature_flags(data_dir="/app/data", service_name="my-service")
    >>>
    >>> # Use throughout application
    >>> flags = get_feature_flags()
    >>> if flags.is_enabled(FeatureFlag.ENABLE_CACHING):
    ...     # Use caching
    ...     pass

Advanced usage with explicit provider:
    >>> from idea_shared.feature_flags import initialize_feature_flags
    >>> from idea_shared.feature_flags.providers import GoFeatureFlagProvider
    >>>
    >>> provider = GoFeatureFlagProvider(endpoint="http://localhost:1031")
    >>> initialize_feature_flags(provider)
"""

from .flags import FeatureFlag, FlagDefaults
from .initialization import init_feature_flags
from .manager import (
    FeatureFlagManager,
    get_feature_flags,
    initialize_feature_flags,
)
from .providers import (
    EnvironmentVariableProvider,
    GoFeatureFlagProvider,
    JsonFileProvider,
)

__all__ = [
    # Core classes
    "FeatureFlagManager",
    # Singleton functions
    "initialize_feature_flags",
    "init_feature_flags",
    "get_feature_flags",
    # Flag definitions
    "FeatureFlag",
    "FlagDefaults",
    # Providers
    "JsonFileProvider",
    "EnvironmentVariableProvider",
    "GoFeatureFlagProvider",
]

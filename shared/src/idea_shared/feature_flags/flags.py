"""Feature flag name constants and default values.

This module defines all available feature flags for IDEA Helsinki services.
Each flag has a constant name and a default value used as fallback.
"""

from enum import StrEnum
from typing import Any


class FeatureFlag(StrEnum):
    """Feature flag name constants.

    Use these constants when evaluating flags to ensure type safety
    and avoid typos in flag names.
    """

    # Validation algorithm flags
    ENABLE_EXPERIMENTAL_VALIDATION = "enable_experimental_validation"
    ENABLE_PARALLEL_PROCESSING = "enable_parallel_processing"

    # Performance optimization flags
    ENABLE_SEGMENT_CACHING = "enable_segment_caching"
    ENABLE_BATCH_PROCESSING = "enable_batch_processing"

    # Logging and debugging flags
    ENABLE_ENHANCED_LOGGING = "enable_enhanced_logging"
    ENABLE_DEBUG_METRICS = "enable_debug_metrics"

    # Configuration override flags
    FCD_UPDATE_INTERVAL_OVERRIDE = "fcd_update_interval_override"
    DISTURBANCE_UPDATE_INTERVAL_OVERRIDE = "disturbance_update_interval_override"


class FlagDefaults:
    """Default values for feature flags.

    These defaults are used when a flag is not defined in the provider
    or when flag evaluation fails.
    """

    # Boolean flag defaults
    ENABLE_EXPERIMENTAL_VALIDATION: bool = False
    ENABLE_PARALLEL_PROCESSING: bool = True
    ENABLE_SEGMENT_CACHING: bool = False
    ENABLE_BATCH_PROCESSING: bool = False
    ENABLE_ENHANCED_LOGGING: bool = False
    ENABLE_DEBUG_METRICS: bool = False

    # Numeric flag defaults (None means no override)
    FCD_UPDATE_INTERVAL_OVERRIDE: int | None = None
    DISTURBANCE_UPDATE_INTERVAL_OVERRIDE: int | None = None

    @classmethod
    def get_default(cls, flag: FeatureFlag) -> Any:
        """Get the default value for a feature flag.

        Args:
            flag: The feature flag to get the default for

        Returns:
            The default value for the flag

        Raises:
            AttributeError: If the flag doesn't have a defined default
        """
        return getattr(cls, flag.value.upper())

"""GoFeatureFlag provider wrapper.

This provider connects to a GoFeatureFlag relay proxy for centralized
feature flag management across all IDEA-Helsinki services.

See: https://gofeatureflag.org/docs/relay-proxy/
"""

import logging

from gofeatureflag_python_provider.options import GoFeatureFlagOptions
from gofeatureflag_python_provider.provider import (
    GoFeatureFlagProvider as GOFFProvider,
)
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails
from openfeature.provider import AbstractProvider, Metadata

logger = logging.getLogger(__name__)


class GoFeatureFlagProvider(AbstractProvider):
    """Feature flag provider that connects to GoFeatureFlag relay proxy.

    This provider wraps the official gofeatureflag-python-provider to integrate
    with the centralized GoFeatureFlag relay proxy. The relay proxy handles
    flag storage, caching, and real-time updates.

    Example:
        >>> provider = GoFeatureFlagProvider(
        ...     endpoint="http://gofeatureflag.feature-flags.svc.cluster.local:1031"
        ... )
        >>> initialize_feature_flags(provider)

    Environment variables:
        FEATURE_FLAG_ENDPOINT: The relay proxy endpoint URL
        FEATURE_FLAG_TIMEOUT: Request timeout in milliseconds (default: 3000)
    """

    def __init__(self, endpoint: str, timeout: int = 3000):
        """Initialize the GoFeatureFlag provider.

        Args:
            endpoint: URL of the GoFeatureFlag relay proxy
            timeout: Request timeout in milliseconds (default: 3000)
        """
        self._endpoint = endpoint
        self._timeout = timeout

        options = GoFeatureFlagOptions(endpoint=endpoint)
        self._provider = GOFFProvider(options=options)

        logger.info(
            f"Initialized GoFeatureFlagProvider with endpoint: {endpoint}, "
            f"timeout: {timeout}ms"
        )

    def get_metadata(self) -> Metadata:
        """Get provider metadata."""
        return Metadata(name="GoFeatureFlagProvider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        """Resolve a boolean feature flag.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        return self._provider.resolve_boolean_details(
            flag_key, default_value, evaluation_context
        )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        """Resolve a string feature flag.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        return self._provider.resolve_string_details(
            flag_key, default_value, evaluation_context
        )

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        """Resolve an integer feature flag.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        return self._provider.resolve_integer_details(
            flag_key, default_value, evaluation_context
        )

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        """Resolve a float feature flag.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        return self._provider.resolve_float_details(
            flag_key, default_value, evaluation_context
        )

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: dict,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[dict]:
        """Resolve an object/dict feature flag.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        return self._provider.resolve_object_details(
            flag_key, default_value, evaluation_context
        )

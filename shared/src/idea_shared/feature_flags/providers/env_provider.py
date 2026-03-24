"""Environment variable-based feature flag provider.

This provider reads feature flags from environment variables.
Useful for production deployments and containerized environments.
"""

import logging
import os
import typing
from collections.abc import Mapping, Sequence

from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType, Reason
from openfeature.provider import AbstractProvider, Metadata

logger = logging.getLogger(__name__)


class EnvironmentVariableProvider(AbstractProvider):
    """Feature flag provider that reads from environment variables.

    Environment variables should follow the pattern:
    FEATURE_FLAG_{FLAG_NAME}=value

    Examples:
        FEATURE_FLAG_ENABLE_CACHING=true
        FEATURE_FLAG_MAX_CONNECTIONS=10
        FEATURE_FLAG_LOG_LEVEL=debug

    Boolean values:
        - True: "true", "1", "yes", "on" (case-insensitive)
        - False: "false", "0", "no", "off" (case-insensitive)
    """

    ENV_PREFIX = "FEATURE_FLAG_"

    def __init__(self, prefix: str = ENV_PREFIX):
        """Initialize the environment variable provider.

        Args:
            prefix: Environment variable prefix (default: FEATURE_FLAG_)
        """
        self._prefix = prefix.upper()
        logger.info(f"Initialized environment variable provider with prefix: {prefix}")

    def _get_env_key(self, flag_key: str) -> str:
        """Convert flag key to environment variable name.

        Args:
            flag_key: The flag identifier

        Returns:
            Environment variable name
        """
        return f"{self._prefix}{flag_key.upper()}"

    def get_metadata(self) -> Metadata:
        """Get provider metadata."""
        return Metadata(name="EnvironmentVariableProvider")

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
        env_key = self._get_env_key(flag_key)
        env_value = os.environ.get(env_key)

        if env_value is None:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        # Parse boolean from string
        value = env_value.lower() in ("true", "1", "yes", "on")

        return FlagResolutionDetails(
            value=value,
            reason=Reason.STATIC,
            variant="enabled" if value else "disabled",
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
        env_key = self._get_env_key(flag_key)
        env_value = os.environ.get(env_key)

        if env_value is None:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        return FlagResolutionDetails(
            value=env_value,
            reason=Reason.STATIC,
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
        env_key = self._get_env_key(flag_key)
        env_value = os.environ.get(env_key)

        if env_value is None:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        try:
            value = int(env_value)
            return FlagResolutionDetails(
                value=value,
                reason=Reason.STATIC,
            )
        except ValueError:
            logger.warning(
                f"Invalid integer value for {env_key}={env_value}. "
                f"Using default: {default_value}"
            )
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                variant="default",
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
        env_key = self._get_env_key(flag_key)
        env_value = os.environ.get(env_key)

        if env_value is None:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        try:
            value = float(env_value)
            return FlagResolutionDetails(
                value=value,
                reason=Reason.STATIC,
            )
        except ValueError:
            logger.warning(
                f"Invalid float value for {env_key}={env_value}. "
                f"Using default: {default_value}"
            )
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                variant="default",
            )

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: typing.Union[Sequence[FlagValueType], Mapping[str, FlagValueType]],
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[typing.Union[Sequence[FlagValueType], Mapping[str, FlagValueType]]]:
        """Resolve an object/dict feature flag.

        Note: Environment variables are parsed as JSON strings for objects.

        Args:
            flag_key: The flag identifier
            default_value: The default value if flag is not found
            evaluation_context: Optional context for flag evaluation

        Returns:
            Resolution details containing the flag value
        """
        import json

        env_key = self._get_env_key(flag_key)
        env_value = os.environ.get(env_key)

        if env_value is None:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        try:
            value = json.loads(env_value)
            if not isinstance(value, dict):
                raise ValueError("Parsed value is not a dictionary")
            return FlagResolutionDetails(
                value=value,
                reason=Reason.STATIC,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"Invalid JSON dict for {env_key}={env_value}: {e}. "
                f"Using default: {default_value}"
            )
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                variant="default",
            )

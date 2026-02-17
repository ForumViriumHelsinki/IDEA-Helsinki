"""JSON file-based feature flag provider.

This provider reads feature flags from a JSON file on disk.
Useful for local development and testing.
"""

import logging
from pathlib import Path
from typing import Any

from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata

from idea_shared.threading.file_locks import read_json_with_retry

logger = logging.getLogger(__name__)


class JsonFileProvider(AbstractProvider):
    """Feature flag provider that reads from a JSON file.

    File format:
    {
        "flags": {
            "flag_name": {
                "enabled": true,
                "value": "some_value",  # optional
                "description": "Flag description"  # optional
            }
        }
    }

    For boolean flags, use the "enabled" field.
    For other types, use the "value" field.
    """

    def __init__(self, file_path: str | Path):
        """Initialize the JSON file provider.

        Args:
            file_path: Path to the JSON configuration file
        """
        self._file_path = Path(file_path)
        self._flags: dict[str, Any] = {}
        self._load_flags()

    def _load_flags(self) -> None:
        """Load flags from the JSON file with ESTALE retry for GCS FUSE mounts."""
        data = read_json_with_retry(self._file_path)

        if data is None:
            logger.warning(
                f"Feature flags file not found or unreadable: {self._file_path}. "
                "Using default values."
            )
            return

        # Validate JSON structure
        if not isinstance(data, dict):
            logger.error(
                f"Invalid feature flags file structure: root must be an object, "
                f"got {type(data).__name__}. Using default values."
            )
            return

        flags = data.get("flags", {})
        if not isinstance(flags, dict):
            logger.error(
                f"Invalid feature flags file structure: 'flags' must be an object, "
                f"got {type(flags).__name__}. Using default values."
            )
            return

        self._flags = flags
        logger.info(f"Loaded {len(self._flags)} feature flags from {self._file_path}")

    def get_metadata(self) -> Metadata:
        """Get provider metadata."""
        return Metadata(name="JsonFileProvider")

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
        if flag_key not in self._flags:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        flag_config = self._flags[flag_key]
        value = flag_config.get("enabled", default_value)

        return FlagResolutionDetails(
            value=bool(value),
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
        if flag_key not in self._flags:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        flag_config = self._flags[flag_key]
        value = flag_config.get("value", default_value)

        return FlagResolutionDetails(
            value=str(value),
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
        if flag_key not in self._flags:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        flag_config = self._flags[flag_key]
        value = flag_config.get("value", default_value)

        try:
            return FlagResolutionDetails(
                value=int(value),
                reason=Reason.STATIC,
            )
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid integer value for flag {flag_key}: {value}. "
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
        if flag_key not in self._flags:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        flag_config = self._flags[flag_key]
        value = flag_config.get("value", default_value)

        try:
            return FlagResolutionDetails(
                value=float(value),
                reason=Reason.STATIC,
            )
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid float value for flag {flag_key}: {value}. "
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
        if flag_key not in self._flags:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.DEFAULT,
                variant="default",
            )

        flag_config = self._flags[flag_key]
        value = flag_config.get("value", default_value)

        if not isinstance(value, dict):
            logger.warning(
                f"Invalid dict value for flag {flag_key}: {value}. "
                f"Using default: {default_value}"
            )
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                variant="default",
            )

        return FlagResolutionDetails(
            value=value,
            reason=Reason.STATIC,
        )

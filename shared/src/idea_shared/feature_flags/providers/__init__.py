"""Feature flag providers for different configuration sources."""

from .env_provider import EnvironmentVariableProvider
from .json_provider import JsonFileProvider

# Lazy import for GoFeatureFlagProvider to avoid dependency issues
# when gofeatureflag-python-provider is not installed or has conflicts
_goff_provider = None


def __getattr__(name: str):
    """Lazy import for GoFeatureFlagProvider."""
    global _goff_provider
    if name == "GoFeatureFlagProvider":
        if _goff_provider is None:
            from .goff_provider import GoFeatureFlagProvider

            _goff_provider = GoFeatureFlagProvider
        return _goff_provider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["JsonFileProvider", "EnvironmentVariableProvider", "GoFeatureFlagProvider"]

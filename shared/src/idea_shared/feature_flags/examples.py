"""Example usage patterns for feature flags.

This module demonstrates how to use feature flags in IDEA Helsinki services.
These examples can be used as reference when integrating feature flags.
"""

import logging
from pathlib import Path

from .flags import FeatureFlag
from .manager import get_feature_flags, initialize_feature_flags
from .providers import EnvironmentVariableProvider, JsonFileProvider

logger = logging.getLogger(__name__)


def example_initialization_json():
    """Example: Initialize with JSON file provider.

    Use this for local development and testing.
    """
    # Path to feature flags configuration
    flags_file = Path("data/feature_flags.json")

    # Initialize with JSON provider
    provider = JsonFileProvider(str(flags_file))
    initialize_feature_flags(provider)

    logger.info("Feature flags initialized with JSON provider")


def example_initialization_env():
    """Example: Initialize with environment variable provider.

    Use this for production deployments and containerized environments.
    """
    # Initialize with environment variable provider
    provider = EnvironmentVariableProvider()
    initialize_feature_flags(provider)

    logger.info("Feature flags initialized with environment variable provider")


def example_boolean_flag():
    """Example: Use boolean feature flag to toggle functionality."""
    flags = get_feature_flags()

    # Check if experimental validation is enabled
    if flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION):
        logger.info("Using experimental validation algorithm")
        # Use new algorithm
        result = "experimental_algorithm_result"
    else:
        logger.info("Using standard validation algorithm")
        # Use standard algorithm
        result = "standard_algorithm_result"

    return result


def example_numeric_override():
    """Example: Use numeric flag to override configuration."""
    from idea_shared.lib.Constants.Constants import FCD_UPDATE_FREQUENCY

    flags = get_feature_flags()

    # Check for update interval override
    override = flags.get_int(
        FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=FCD_UPDATE_FREQUENCY
    )

    if override != FCD_UPDATE_FREQUENCY:
        logger.info(f"FCD update interval overridden to {override} minutes")
    else:
        logger.info(
            f"Using default FCD update interval: {FCD_UPDATE_FREQUENCY} minutes"
        )

    return override


def example_performance_optimization():
    """Example: Use flags to control performance optimizations."""
    flags = get_feature_flags()

    # Example data to process
    segments = ["segment1", "segment2", "segment3"]

    # Check if parallel processing is enabled
    if flags.is_enabled(FeatureFlag.ENABLE_PARALLEL_PROCESSING):
        logger.info("Processing segments in parallel")
        # Use parallel processing
        import asyncio

        async def process_parallel():
            tasks = [process_segment_async(s) for s in segments]
            return await asyncio.gather(*tasks)

        # Would run: results = asyncio.run(process_parallel())
        results = ["parallel_processed"] * len(segments)
    else:
        logger.info("Processing segments sequentially")
        # Sequential processing
        results = [process_segment_sync(s) for s in segments]

    return results


def process_segment_async(segment_id: str):
    """Mock async segment processing."""
    import asyncio

    async def _process():
        await asyncio.sleep(0.1)
        return f"processed_{segment_id}"

    return _process()


def process_segment_sync(segment_id: str):
    """Mock sync segment processing."""
    return f"processed_{segment_id}"


def example_caching_with_flag():
    """Example: Implement optional caching based on feature flag."""
    flags = get_feature_flags()

    # Simple in-memory cache
    _cache = {}

    def get_segment_data(segment_id: str):
        """Get segment data with optional caching."""
        # Check if caching is enabled
        if flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING):
            # Use cache
            if segment_id in _cache:
                logger.debug(f"Cache hit for segment {segment_id}")
                return _cache[segment_id]

            # Cache miss - fetch and cache
            data = fetch_segment_data(segment_id)
            _cache[segment_id] = data
            logger.debug(f"Cached data for segment {segment_id}")
            return data
        else:
            # Caching disabled - always fetch fresh
            logger.debug(
                f"Fetching fresh data for segment {segment_id} (cache disabled)"
            )
            return fetch_segment_data(segment_id)

    return get_segment_data


def fetch_segment_data(segment_id: str):
    """Mock data fetching function."""
    return {"segment_id": segment_id, "data": "example_data"}


def example_enhanced_logging():
    """Example: Enable detailed logging based on feature flag."""
    flags = get_feature_flags()

    def process_with_logging(data):
        """Process data with optional enhanced logging."""
        logger.info("Starting data processing")

        if flags.is_enabled(FeatureFlag.ENABLE_ENHANCED_LOGGING):
            # Detailed logging enabled
            logger.debug(f"Input data: {data}")
            logger.debug("Step 1: Validation")

        # Processing logic
        result = {"processed": data}

        if flags.is_enabled(FeatureFlag.ENABLE_ENHANCED_LOGGING):
            logger.debug(f"Processing result: {result}")
            logger.debug("Step 2: Complete")

        logger.info("Data processing complete")
        return result

    return process_with_logging


def example_service_initialization():
    """Example: Complete service initialization with feature flags.

    This shows how to initialize feature flags at service startup.
    """
    import os

    # Determine which provider to use based on environment
    environment = os.getenv("ENVIRONMENT", "development")

    if environment == "production":
        # Production: Use environment variables
        logger.info("Initializing feature flags for production (env vars)")
        provider = EnvironmentVariableProvider()
    else:
        # Development/Testing: Use JSON file
        logger.info("Initializing feature flags for development (JSON file)")
        flags_file = Path("data/feature_flags.json")

        # Fall back to example file if main file doesn't exist
        if not flags_file.exists():
            flags_file = Path("data/feature_flags.example.json")
            logger.warning(f"Using example flags file: {flags_file}")

        provider = JsonFileProvider(str(flags_file))

    # Initialize global feature flags
    initialize_feature_flags(provider)

    # Log active experimental features
    flags = get_feature_flags()
    experimental_flags = [
        FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION,
        FeatureFlag.ENABLE_SEGMENT_CACHING,
        FeatureFlag.ENABLE_BATCH_PROCESSING,
    ]

    active_experiments = [
        flag.value for flag in experimental_flags if flags.is_enabled(flag)
    ]

    if active_experiments:
        logger.warning(f"Active experimental features: {', '.join(active_experiments)}")
    else:
        logger.info("No experimental features enabled")


def example_gradual_rollout():
    """Example: Gradual feature rollout (for future use).

    This shows how context-aware evaluation could be used for
    gradual rollouts or A/B testing.
    """
    from openfeature.evaluation_context import EvaluationContext

    flags = get_feature_flags()

    def should_use_new_feature(segment_id: str, environment: str) -> bool:
        """Determine if new feature should be used for this segment.

        In the future, this could use context to enable features for:
        - Specific segments (canary testing)
        - Specific environments
        - Percentage-based rollouts
        """
        # Create evaluation context
        context = EvaluationContext(segment_id=segment_id, environment=environment)

        # Evaluate flag with context
        # Note: Basic providers ignore context, but cloud providers use it
        return flags.is_enabled(
            FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION, context=context
        )

    # Example usage
    segment_id = "segment_12345"
    environment = "production"

    if should_use_new_feature(segment_id, environment):
        logger.info(f"New feature enabled for {segment_id}")
    else:
        logger.info(f"Using standard feature for {segment_id}")


if __name__ == "__main__":
    """Run examples (for demonstration purposes)."""
    logging.basicConfig(level=logging.INFO)

    print("=== Example: Service Initialization ===")
    example_service_initialization()

    print("\n=== Example: Boolean Flag ===")
    example_boolean_flag()

    print("\n=== Example: Numeric Override ===")
    example_numeric_override()

    print("\n=== Example: Performance Optimization ===")
    example_performance_optimization()

    print("\n=== Example: Caching ===")
    get_data = example_caching_with_flag()
    get_data("test_segment")

    print("\n=== Example: Enhanced Logging ===")
    process = example_enhanced_logging()
    process({"test": "data"})

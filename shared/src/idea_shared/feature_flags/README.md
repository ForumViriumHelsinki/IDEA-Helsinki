# Feature Flags for IDEA Helsinki

OpenFeature-based feature flag system for controlling features and configuration across IDEA Helsinki services.

## Requirements

- **Python**: 3.12 or higher
- **Dependencies**: OpenFeature SDK 0.6.0+ (automatically installed with `idea-shared`)

The feature flag system uses Python 3.12+ features including:
- Modern type annotations (`dict[str, Any]`, `int | None`)
- Enhanced pattern matching capabilities
- Improved error messages

## Overview

This module provides a vendor-neutral feature flag implementation using the [OpenFeature](https://openfeature.dev/) standard. It supports multiple providers (JSON files, environment variables) and can be easily extended to support cloud-based flag services.

## Quick Start

### 1. Initialize Feature Flags

At your service's startup (e.g., in `main.py`):

```python
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import JsonFileProvider

# Use JSON file provider (development/local)
provider = JsonFileProvider("data/feature_flags.json")
initialize_feature_flags(provider)

# OR use environment variable provider (production/containers)
from idea_shared.feature_flags.providers import EnvironmentVariableProvider
provider = EnvironmentVariableProvider()
initialize_feature_flags(provider)
```

### 2. Use Feature Flags

Throughout your application:

```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

flags = get_feature_flags()

# Boolean flags
if flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION):
    result = experimental_validate(segment)
else:
    result = standard_validate(segment)

# Numeric flags
max_retries = flags.get_int(FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE, default=5)

# String flags
log_level = flags.get_string("log_level", default="INFO")

# Object/dict flags
config = flags.get_object("advanced_config", default={})
```

## Providers

### JSON File Provider

Best for: Local development, testing, configuration files

**File format** (`data/feature_flags.json`):
```json
{
  "flags": {
    "enable_caching": {
      "enabled": true,
      "description": "Enable in-memory caching"
    },
    "max_connections": {
      "value": 100,
      "description": "Maximum number of connections"
    }
  }
}
```

**Usage**:
```python
from idea_shared.feature_flags.providers import JsonFileProvider

provider = JsonFileProvider("data/feature_flags.json")
```

**Features**:
- Human-readable configuration
- Easy to version control
- Supports hot-reload in development (future enhancement)
- Graceful fallback if file missing or invalid

### Environment Variable Provider

Best for: Production deployments, containerized environments, CI/CD

**Format**:
```bash
# Boolean flags (case-insensitive values)
FEATURE_FLAG_ENABLE_CACHING=true
FEATURE_FLAG_ENABLE_LOGGING=false

# Numeric flags
FEATURE_FLAG_MAX_CONNECTIONS=100
FEATURE_FLAG_THRESHOLD=0.75

# String flags
FEATURE_FLAG_LOG_LEVEL=debug

# Object flags (JSON)
FEATURE_FLAG_CONFIG='{"key": "value", "nested": {"data": 123}}'
```

**Usage**:
```python
from idea_shared.feature_flags.providers import EnvironmentVariableProvider

# Default prefix: FEATURE_FLAG_
provider = EnvironmentVariableProvider()

# Custom prefix
provider = EnvironmentVariableProvider(prefix="MY_APP_")
```

**Boolean parsing**:
- True: `"true"`, `"1"`, `"yes"`, `"on"` (case-insensitive)
- False: `"false"`, `"0"`, `"no"`, `"off"` (case-insensitive)

## Available Flags

All flags are defined in `flags.py` as type-safe constants:

### Validation Algorithm Flags
- `ENABLE_EXPERIMENTAL_VALIDATION` - Toggle experimental validation algorithms
- `ENABLE_PARALLEL_PROCESSING` - Process multiple segments in parallel (default: True)

### Performance Optimization Flags
- `ENABLE_SEGMENT_CACHING` - Cache FCD segment geometries in memory
- `ENABLE_BATCH_PROCESSING` - Enable batch processing mode

### Logging and Debugging Flags
- `ENABLE_ENHANCED_LOGGING` - Detailed debug logging
- `ENABLE_DEBUG_METRICS` - Collect detailed performance metrics

### Configuration Override Flags
- `FCD_UPDATE_INTERVAL_OVERRIDE` - Override FCD update frequency (minutes)
- `DISTURBANCE_UPDATE_INTERVAL_OVERRIDE` - Override disturbance update frequency

## Adding New Flags

### 1. Define the Flag

Edit `flags.py`:

```python
class FeatureFlag(str, Enum):
    # ... existing flags ...
    ENABLE_MY_FEATURE = "enable_my_feature"

class FlagDefaults:
    # ... existing defaults ...
    ENABLE_MY_FEATURE: bool = False
```

### 2. Update Configuration

For JSON provider, add to `data/feature_flags.json`:
```json
{
  "flags": {
    "enable_my_feature": {
      "enabled": false,
      "description": "Description of my feature"
    }
  }
}
```

For environment variables:
```bash
FEATURE_FLAG_ENABLE_MY_FEATURE=true
```

### 3. Use the Flag

```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

flags = get_feature_flags()
if flags.is_enabled(FeatureFlag.ENABLE_MY_FEATURE):
    # Your feature code
    pass
```

## Integration Patterns

### Pattern 1: Direct Feature Toggling

```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

def process_segment(segment):
    flags = get_feature_flags()

    if flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION):
        return experimental_algorithm(segment)
    else:
        return standard_algorithm(segment)
```

### Pattern 2: Configuration Override

```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag
from lib.Constants.Constants import FCD_UPDATE_FREQUENCY

def get_update_interval():
    flags = get_feature_flags()

    # Check if override is set
    override = flags.get_int(
        FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE,
        default=None
    )

    return override if override is not None else FCD_UPDATE_FREQUENCY
```

### Pattern 3: Gradual Rollout (Future)

```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag
from openfeature.evaluation_context import EvaluationContext

def process_with_context(segment_id):
    flags = get_feature_flags()

    # Context-aware evaluation (for A/B testing, gradual rollouts)
    context = EvaluationContext(
        segment_id=segment_id,
        environment="production"
    )

    if flags.is_enabled(FeatureFlag.ENABLE_CACHING, context=context):
        # Feature enabled for this segment
        pass
```

## Docker and Kubernetes Integration

### Kubernetes with Skaffold (IDEA Helsinki)

**IMPORTANT**: The `data/` directory must be mounted as a volume in your Kubernetes deployments for JSON-based feature flags to work. All three IDEA Helsinki service deployments (`k8s/*-deployment.yaml`) already have this configured:

```yaml
spec:
  containers:
  - name: service-name
    volumeMounts:
    - name: data-volume
      mountPath: /app/data
  volumes:
  - name: data-volume
    hostPath:
      path: /Users/your-user/repos/IDEA-Helsinki/data
      type: Directory
```

This enables:
- Real-time feature flag updates (changes take effect after pod restart)
- Shared configuration across all services
- No need to rebuild containers when toggling features

**Usage:**
1. Edit `data/feature_flags.json` locally
2. Restart the pod: `kubectl rollout restart deployment/<service-name> -n idea-helsinki`
3. Changes take effect immediately

### Docker Compose

```yaml
services:
  orchestrator:
    # Option 1: Environment variables
    environment:
      - FEATURE_FLAG_ENABLE_CACHING=true
      - FEATURE_FLAG_MAX_CONNECTIONS=50
      - FEATURE_FLAG_LOG_LEVEL=debug
    # Option 2: Mount JSON file
    volumes:
      - ./data:/app/data:ro
```

### Dockerfile

```dockerfile
# Option 1: Environment variables
ENV FEATURE_FLAG_ENABLE_CACHING=true

# Option 2: Copy JSON file (not recommended for development)
COPY data/feature_flags.json /app/data/feature_flags.json
```

## Testing

### Unit Tests

```python
import pytest
from idea_shared.feature_flags import FeatureFlagManager
from idea_shared.feature_flags.providers import JsonFileProvider

def test_my_feature_flag(tmp_path):
    # Create test flag file
    flag_file = tmp_path / "flags.json"
    flag_file.write_text('{"flags": {"my_flag": {"enabled": true}}}')

    # Initialize manager
    provider = JsonFileProvider(str(flag_file))
    manager = FeatureFlagManager(provider)

    # Test flag evaluation
    assert manager.is_enabled("my_flag", default=False) is True
```

### Override in Tests

```python
import os
import pytest

@pytest.fixture
def enable_test_features():
    """Enable features for testing."""
    os.environ["FEATURE_FLAG_ENABLE_CACHING"] = "true"
    yield
    del os.environ["FEATURE_FLAG_ENABLE_CACHING"]

def test_with_feature_enabled(enable_test_features):
    # Test with feature enabled
    pass
```

## Best Practices

1. **Always provide defaults**: Every flag evaluation should have a sensible default value
2. **Use enum constants**: Use `FeatureFlag` enum for type safety and IDE autocomplete
3. **Document flags**: Add descriptions in JSON files to explain what each flag does
4. **Keep flags temporary**: Feature flags are for gradual rollouts, not permanent configuration
5. **Clean up old flags**: Remove flags once features are fully deployed or rolled back
6. **Test both states**: Write tests for both enabled and disabled states
7. **Initialize once**: Call `initialize_feature_flags()` once at application startup
8. **Don't overuse**: Not every configuration needs to be a flag; use for features you might toggle

## Migrating to Cloud Providers

The OpenFeature standard makes it easy to swap providers. To migrate to a cloud service:

```python
# Example: LaunchDarkly (hypothetical)
from openfeature_launchdarkly import LaunchDarklyProvider

provider = LaunchDarklyProvider(sdk_key="your-key")
initialize_feature_flags(provider)

# No changes needed to flag evaluation code!
flags = get_feature_flags()
if flags.is_enabled(FeatureFlag.ENABLE_CACHING):
    pass
```

Popular OpenFeature providers:
- **Flagsmith** - Open source, self-hosted or cloud
- **LaunchDarkly** - Enterprise feature management
- **Split** - Feature experimentation platform
- **ConfigCat** - Simple feature flag service

## Migration Guide

### Integrating into Existing Services

This guide helps you add feature flags to existing IDEA Helsinki services (orchestrator, fcd-manager, traffic-monitor).

#### Step 1: Install Dependencies

Dependencies are already included in `idea-shared`. If you're using `uv`:

```bash
cd services/your-service
uv pip install -e ../../shared
```

#### Step 2: Create Feature Flag Configuration

Copy the example configuration:

```bash
# From repository root
cp data/feature_flags.example.json data/feature_flags.json
```

Edit `data/feature_flags.json` to enable/disable features for your needs.

#### Step 3: Initialize at Service Startup

Add initialization code to your service's main entry point (usually `main.py` or equivalent):

```python
import logging
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import JsonFileProvider

logger = logging.getLogger(__name__)

def main():
    # Initialize feature flags early in startup
    try:
        provider = JsonFileProvider("data/feature_flags.json")
        initialize_feature_flags(provider)
        logger.info("Feature flags initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize feature flags: {e}")
        logger.warning("Continuing with default flag values")

    # Rest of your service initialization
    ...
```

#### Step 4: Replace Hardcoded Configuration

Find places in your code where configuration is hardcoded or loaded from Constants:

**Before:**
```python
from lib.Constants.Constants import FCD_UPDATE_FREQUENCY

# Hardcoded configuration
update_interval = FCD_UPDATE_FREQUENCY  # Always 5 minutes
enable_caching = False  # Always disabled
```

**After:**
```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag
from lib.Constants.Constants import FCD_UPDATE_FREQUENCY

flags = get_feature_flags()

# Configuration from feature flags with fallback
update_interval = flags.get_int(
    FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE,
    default=FCD_UPDATE_FREQUENCY
)
enable_caching = flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING)
```

#### Step 5: Toggle Experimental Features

Use flags to safely enable experimental features:

**Before:**
```python
def process_segment(segment):
    return standard_algorithm(segment)
```

**After:**
```python
from idea_shared.feature_flags import get_feature_flags, FeatureFlag

def process_segment(segment):
    flags = get_feature_flags()

    if flags.is_enabled(FeatureFlag.ENABLE_EXPERIMENTAL_VALIDATION):
        return experimental_algorithm(segment)
    else:
        return standard_algorithm(segment)
```

#### Step 6: Production Deployment with Environment Variables

For Kubernetes/Docker deployments, switch to environment variables:

**Update Dockerfile:**
```dockerfile
FROM python:3.12-slim

# Copy and install dependencies
COPY shared/ /app/shared/
RUN pip install -e /app/shared

# No need to copy feature_flags.json - use environment variables
COPY services/your-service /app/

CMD ["python", "-m", "your_service.main"]
```

**Update main.py for production:**
```python
import os
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import (
    JsonFileProvider,
    EnvironmentVariableProvider
)

def main():
    # Use environment variables in production, JSON in development
    if os.getenv("ENVIRONMENT") == "production":
        provider = EnvironmentVariableProvider()
    else:
        provider = JsonFileProvider("data/feature_flags.json")

    initialize_feature_flags(provider)
    ...
```

**Update Kubernetes ConfigMap:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: feature-flags
data:
  FEATURE_FLAG_ENABLE_PARALLEL_PROCESSING: "true"
  FEATURE_FLAG_ENABLE_SEGMENT_CACHING: "true"
  FEATURE_FLAG_FCD_UPDATE_INTERVAL_OVERRIDE: "10"
```

#### Step 7: Testing

Write tests that verify behavior with different flag values:

```python
import pytest
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import JsonFileProvider

def test_with_experimental_feature_enabled():
    """Test behavior with experimental feature enabled."""
    import tempfile
    import json

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
        json.dump({
            "flags": {
                "enable_experimental_validation": {"enabled": True}
            }
        }, f)
        f.flush()

        provider = JsonFileProvider(f.name)
        initialize_feature_flags(provider)

        # Test your code with feature enabled
        result = process_segment(test_segment)
        assert result.uses_experimental_algorithm
```

### Common Integration Patterns

#### Pattern 1: Gradual Rollout

```python
# Enable feature for testing, disable for production initially
flags = get_feature_flags()

if flags.is_enabled(FeatureFlag.ENABLE_BATCH_PROCESSING):
    use_batch_processor()
else:
    use_single_processor()
```

#### Pattern 2: Performance Optimization

```python
# Cache only if enabled
flags = get_feature_flags()

if flags.is_enabled(FeatureFlag.ENABLE_SEGMENT_CACHING):
    segment = cache.get_or_fetch(segment_id)
else:
    segment = fetch_segment(segment_id)
```

#### Pattern 3: Configuration Override

```python
# Override constants without code changes
flags = get_feature_flags()

update_interval = flags.get_int(
    FeatureFlag.FCD_UPDATE_INTERVAL_OVERRIDE,
    default=Constants.FCD_UPDATE_FREQUENCY
)
```

## Troubleshooting

### Flags not taking effect

1. **Check initialization**: Ensure `initialize_feature_flags()` is called at startup
2. **Check provider**: Verify JSON file exists or environment variables are set
3. **Check flag names**: Flag names must match exactly (case-sensitive in JSON)
4. **Check logs**: Provider logs warnings for invalid configurations
5. **Check volume mount (Kubernetes/Skaffold)**: Verify `data/` directory is mounted in pod:
   ```bash
   kubectl exec -n idea-helsinki deployment/<service-name> -- ls -la /app/data
   ```
   If you see "No such file or directory", the volume mount is not configured. See [Kubernetes Integration](#kubernetes-with-skaffold-idea-helsinki) above.

### RuntimeError: Feature flags not initialized

Call `initialize_feature_flags()` before using `get_feature_flags()`:

```python
# At startup
from idea_shared.feature_flags import initialize_feature_flags
from idea_shared.feature_flags.providers import JsonFileProvider

provider = JsonFileProvider("data/feature_flags.json")
initialize_feature_flags(provider)

# Later, anywhere in code
from idea_shared.feature_flags import get_feature_flags
flags = get_feature_flags()  # Now works!
```

### Default values being used

1. For JSON provider: Check file exists and is valid JSON
2. For environment provider: Check variable name format (`FEATURE_FLAG_` prefix)
3. Check logs for parsing errors (invalid types, malformed JSON)

## Further Reading

- [OpenFeature Documentation](https://openfeature.dev/docs/)
- [Feature Flag Best Practices](https://www.statsig.com/perspectives/feature-flagging-python-best-practices)
- [Five Minutes to Feature Flags](https://openfeature.dev/docs/tutorials/five-minutes-to-feature-flags)

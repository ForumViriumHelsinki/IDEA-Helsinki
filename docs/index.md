# IDEA-Helsinki

Traffic validation system for analyzing the impact of traffic disturbances on road segments in Helsinki.

## Services

IDEA-Helsinki is composed of three microservices:

| Service | Purpose |
|---------|---------|
| **Orchestrator** | Main async orchestration for IDEA validation |
| **FCD Manager** | FCD data synchronization from Azure to InfluxDB |
| **Traffic Monitor** | Traffic disturbance monitoring and spatial intersection detection |

## Quick Start

```bash
# Install dependencies
uv sync --all-packages --all-extras

# Run locally with Skaffold
dotenvx run -- skaffold dev

# Run tests
just test
```

## Documentation

- [Architecture Overview](program_schematic.md) - System design and data flow
- [Data Models](data_models.md) - Core data structures
- [Versioning](VERSIONING.md) - Release strategy
- [API Reference](api/) - Auto-generated from docstrings

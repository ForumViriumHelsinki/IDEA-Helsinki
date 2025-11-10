# Versioning Strategy

IDEA-Helsinki uses **unified versioning** for all components. The shared library and all three microservices share a single version number, ensuring perfect compatibility and simplifying deployment.

## Current Approach: Linked Versioning

All components move together:
- **idea-shared** (shared library)
- **orchestrator** (service)
- **fcd-manager** (service)
- **traffic-monitor** (service)

**Example:** When the system is at `v0.9.0`, all four components are at `v0.9.0`.

## Why Unified Versioning?

### 1. Matches Deployment Reality
All services are deployed together as a cohesive system. Docker containers are built and deployed atomically, so versioning reflects this reality.

### 2. Living at HEAD Development
Services depend on the adjacent shared library code (editable installs). There's no independent versioning in development, so releases shouldn't pretend there is.

### 3. Eliminates Version Drift
Impossible for the shared library to get out of sync with services. No compatibility matrix to maintain.

### 4. Simpler Mental Model
One version = complete system state. Easier to reason about, easier to rollback, easier to communicate.

### 5. Automatic Coordination
Release-please handles everything. No manual coordination needed when breaking changes occur.

## Semantic Versioning

IDEA-Helsinki follows [Semantic Versioning 2.0.0](https://semver.org/):

### MAJOR version (X.0.0)
**Breaking changes** - incompatible API modifications

**Examples:**
- Breaking change in shared library API
- Incompatible data format changes
- Removal of deprecated features
- Database schema changes requiring migration

**Impact:** All services bump MAJOR version together (even if unchanged)

### MINOR version (0.X.0)
**New features** - backward compatible additions

**Examples:**
- New shared library features
- New service endpoints or capabilities
- New optional configuration parameters
- Feature additions without breaking existing behavior

**Impact:** All services bump MINOR version together

### PATCH version (0.0.X)
**Bug fixes** - backward compatible fixes

**Examples:**
- Bug fixes in shared library
- Service-specific bug fixes
- Documentation updates
- Performance improvements without API changes

**Impact:** All services bump PATCH version together

## Release Process

### Automated via release-please

1. **Conventional commits** trigger version bumps:
   - `feat:` → MINOR version bump
   - `fix:` → PATCH version bump
   - `feat!:` or `BREAKING CHANGE:` → MAJOR version bump

2. **Release-please creates PR** with:
   - Updated version in all `pyproject.toml` files
   - Consolidated CHANGELOG.md entries
   - GitHub release draft

3. **Merge PR** to trigger:
   - GitHub release publication
   - Docker image builds with version labels
   - Deployment of new version

### Component-Specific Changes in Changelog

Even though all components share a version, the changelog shows what actually changed:

```markdown
## [0.10.0] - 2025-01-15

### idea-shared
- feat: add new spatial analysis algorithm

### orchestrator
- fix: correct worker shutdown sequence

### fcd-manager
- No changes in this release

### traffic-monitor
- fix: handle malformed WFS responses
```

Use conventional commit **scopes** to indicate component:
- `feat(shared): add new algorithm` → Shows in idea-shared section
- `fix(orchestrator): correct shutdown` → Shows in orchestrator section
- `feat(fcd-manager): support new format` → Shows in fcd-manager section

## Docker Image Versioning

### Build Arguments
Docker builds accept a `VERSION` argument:

```bash
docker build --build-arg VERSION=0.9.0 -f services/orchestrator/Dockerfile .
```

### Version Metadata in Images

**Docker labels** (inspect with `docker inspect`):
```
org.idea-helsinki.version=0.9.0
org.opencontainers.image.version=0.9.0
```

**Version file** (read at runtime):
```
/app/VERSION
```

Services can expose version via health checks or metrics.

### Local Development
When building locally without `VERSION` arg, defaults to `dev`:

```bash
docker build -f services/orchestrator/Dockerfile .
# Results in VERSION=dev
```

## Development Workflow

### Making Changes

1. **Make your changes** in shared library or services
2. **Use conventional commits**:
   ```bash
   git commit -m "feat(shared): add intersection caching"
   git commit -m "fix(orchestrator): handle timeout gracefully"
   git commit -m "feat(traffic-monitor)!: change API response format"
   ```

3. **Push to main** (or create PR)
4. **Release-please detects** conventional commits and determines version bump
5. **Merge release PR** when ready to release

### Breaking Changes

When making a breaking change in **any** component:

1. **Use breaking change syntax**:
   ```bash
   git commit -m "feat(shared)!: redesign segment API"
   # OR
   git commit -m "feat(shared): redesign segment API

   BREAKING CHANGE: Segment.get_geometry() now returns GeoJSON instead of WKT"
   ```

2. **Update all affected code** in the same PR:
   - If shared library API changes, update all services that use it
   - All tests must pass with the breaking change

3. **Release-please creates MAJOR version bump**:
   - All components go from v0.9.0 → v1.0.0

### Non-Breaking Changes

For bug fixes or backward-compatible features:

1. **Make changes** in any component
2. **Use standard conventional commits**:
   ```bash
   git commit -m "fix(fcd-manager): handle missing timestamps"
   git commit -m "feat(shared): add optional caching parameter"
   ```

3. **Release-please handles automatically**:
   - PATCH bump for fixes (0.9.0 → 0.9.1)
   - MINOR bump for features (0.9.0 → 0.10.0)

## Querying Version Information

### From Docker Image

```bash
# Inspect labels
docker inspect orchestrator:latest | jq '.[0].Config.Labels'

# Read version file
docker run orchestrator:latest cat /app/VERSION
```

### From Running Container

```bash
# Read version file
kubectl exec -it orchestrator-pod -- cat /app/VERSION

# Check labels (if exposed via health check)
curl http://orchestrator:8080/health
```

### From Git Repository

```bash
# Latest release version
cat .release-please-manifest.json

# Component-specific version (should all match)
jq '.shared' .release-please-manifest.json
jq '."services/orchestrator"' .release-please-manifest.json
```

## Migration from Previous Approach

**Before:** Services at v0.9.0, shared library at v0.6.0 (version drift)

**After:** All components unified at v0.9.0

**Next release:** All components bump together (e.g., v0.9.0 → v0.10.0)

## Future Considerations

### If Components Need Independence

If in the future you need to version components independently:

1. **Remove `idea-shared` from linked-versions** in `release-please-config.json`
2. **Add version constraints** in service `pyproject.toml`:
   ```toml
   dependencies = [
       "idea-shared>=0.9.0,<1.0.0"
   ]
   ```
3. **Publish shared library** to internal package index
4. **Accept complexity** of version compatibility matrix

However, this is **not recommended** for tightly coupled monorepo services.

### Workspace Tools

Monitor uv workspace development. When workspace builds are supported:
- Consider migrating to `uv` workspace
- Single `uv.lock` for entire project
- Automatic editable dependencies
- Simplified dependency management

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [release-please documentation](https://github.com/googleapis/release-please)
- [Monorepo versioning best practices](https://github.com/googleapis/release-please/blob/main/docs/customizing.md#versioning-strategies)

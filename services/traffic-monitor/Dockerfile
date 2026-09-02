# Interpreter version for BOTH stages. They must never diverge: the runtime stage
# copies the builder's /app/.venv, whose site-packages live in
# lib/python${PYTHON_VERSION}/ and whose C extensions carry that version's ABI
# tag. A split leaves the venv entirely off sys.path and every import fails
# (0.30.9 shipped a 3.12 venv onto a 3.14 runtime and crash-looped in prod).
ARG PYTHON_VERSION=3.12

# uv is copied in as a binary so the builder and runtime share one base image.
FROM ghcr.io/astral-sh/uv:0.12.7 AS uv

FROM python:${PYTHON_VERSION}-alpine AS build
COPY --from=uv /uv /uvx /bin/

# Install build dependencies for geospatial packages
RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    linux-headers \
    geos-dev \
    proj-dev \
    gdal-dev

WORKDIR /app

# Copy workspace root config + lockfile
COPY pyproject.toml uv.lock ./

# Copy member pyproject.toml files for workspace resolution
COPY shared/pyproject.toml shared/pyproject.toml
COPY services/orchestrator/pyproject.toml services/orchestrator/pyproject.toml
COPY services/fcd-manager/pyproject.toml services/fcd-manager/pyproject.toml
COPY services/traffic-monitor/pyproject.toml services/traffic-monitor/pyproject.toml

# Install third-party deps only (cacheable layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package traffic-monitor --no-install-workspace --no-editable

# Copy source and install workspace packages
COPY shared/ shared/
COPY services/traffic-monitor/ services/traffic-monitor/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package traffic-monitor --no-editable

FROM python:${PYTHON_VERSION}-alpine AS runtime

# Version metadata (set during build)
ARG VERSION=dev
LABEL org.idea-helsinki.version="${VERSION}"
LABEL org.opencontainers.image.version="${VERSION}"

# Install system dependencies for geospatial processing
RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    linux-headers \
    geos-dev \
    proj-dev \
    gdal-dev

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /app/.venv /app/.venv

# Copy source code
COPY --from=build /app/services/traffic-monitor/src /app/src

# Create version file
ARG VERSION=dev
RUN echo "${VERSION}" > /app/VERSION

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

# Run the application using the venv Python directly
CMD ["/app/.venv/bin/python", "src/main.py"]

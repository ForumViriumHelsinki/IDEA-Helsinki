FROM ghcr.io/astral-sh/uv:python3.12-alpine AS build

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
COPY services/traffic-monitor/pyproject.toml services/traffic-monitor/pyproject.toml

# Install third-party deps only (cacheable layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package traffic-monitor --no-install-workspace --no-editable

# Copy source and install workspace packages
COPY shared/ shared/
COPY services/traffic-monitor/ services/traffic-monitor/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package traffic-monitor --no-editable

FROM python:3.12-alpine AS runtime

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

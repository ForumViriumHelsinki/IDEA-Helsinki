FROM python:3.12-alpine AS build

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy shared package and service, preserving repo directory structure
# so that the relative path "../../shared" in pyproject.toml resolves naturally
COPY shared/ ./shared/
COPY services/orchestrator/ ./services/orchestrator/

# Build from the service directory where pyproject.toml lives
WORKDIR /app/services/orchestrator

# Create virtual environment and install dependencies
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e ../../shared && \
    uv pip install -e .

FROM python:3.12-alpine AS runtime

# Version metadata (set during build)
ARG VERSION=dev
LABEL org.idea-helsinki.version="${VERSION}"
LABEL org.opencontainers.image.version="${VERSION}"

# Install system dependencies for geospatial packages if needed
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /app/services/orchestrator/.venv /app/.venv

# Copy source code
COPY --from=build /app/services/orchestrator/src /app/src

# Copy shared module
COPY --from=build /app/shared /app/shared

# Create version file
ARG VERSION=dev
RUN echo "${VERSION}" > /app/VERSION

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

# Install uv in runtime
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv

# Run the application using uv
CMD ["uv", "run", "python", "src/main.py"]

FROM python:3.12-alpine AS build

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy shared package first
COPY shared/ ./shared/

# Copy service package and dependencies
COPY services/fcd-manager/pyproject.toml .
COPY services/fcd-manager/src/ ./src/

# Create virtual environment and install dependencies
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -e ./shared && \
    uv pip install -e .

FROM python:3.12-alpine AS runtime

# Install system dependencies for data processing
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers

# Create non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

# Copy virtual environment from build stage
COPY --from=build /app/.venv /app/.venv

# Copy source code
COPY --from=build /app/src /app/src

# Copy shared module
COPY --from=build /app/shared /app/shared

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

# Install uv in runtime
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv

# Run the application using uv
CMD ["uv", "run", "python", "src/main.py"]

#!/bin/zsh

# ==============================================================================
# InfluxDB Stop Script
# ==============================================================================
# This script stops the running InfluxDB container.
# ==============================================================================

# The name of the container to stop
CONTAINER_NAME="tfds-fcd-influxdb-container"

# Check if the container is actually running
if [ ! "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' is not running."
    exit 0
fi

# Stop the container
echo "Stopping InfluxDB container '$CONTAINER_NAME'..."
docker stop "$CONTAINER_NAME"

echo "Container '$CONTAINER_NAME' stopped."

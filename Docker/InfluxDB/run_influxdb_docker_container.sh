#!/bin/zsh

# ==============================================================================
# InfluxDB Start Script
# ==============================================================================
# This script starts the existing InfluxDB container.
# It will not re-initialize or change any settings.
# ==============================================================================

# The name of the container to start
CONTAINER_NAME="tfds-fcd-influxdb-container"

# Check if the container exists
if [ ! "$(docker ps -a -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Error: Container '$CONTAINER_NAME' not found."
    echo "Please run the 'init_run_influxdb_docker_container.sh' script first to create it."
    exit 1
fi

# Check if the container is already running
if [ "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' is already running."
    exit 0
fi

# Start the container if it is stopped
echo "Starting existing InfluxDB container '$CONTAINER_NAME'..."
docker start "$CONTAINER_NAME"

echo "Container started. Access UI at http://localhost:8086"

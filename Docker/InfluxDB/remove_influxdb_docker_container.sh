#!/bin/zsh

# ==============================================================================
# InfluxDB Removal Script
# ==============================================================================
# This script stops and removes the InfluxDB container.
#
# IMPORTANT: This will NOT delete your database data, which is stored
# on the external hard drive. It only removes the container itself.
# You can always recreate it later using 'init-influx.sh'.
# ==============================================================================

# The name of the container to stop
CONTAINER_NAME="tfds-fcd-influxdb-container"

# Check if the container exists
if [ ! "$(docker ps -a -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Container '$CONTAINER_NAME' does not exist. Nothing to do."
    exit 0
fi

# Stop the container if it is running
if [ "$(docker ps -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Stopping container '$CONTAINER_NAME'..."
    docker stop "$CONTAINER_NAME"
fi

# Remove the container
echo "Removing container '$CONTAINER_NAME'..."
docker rm "$CONTAINER_NAME"

echo "Container '$CONTAINER_NAME' has been successfully removed."

#!/bin/zsh

# ==============================================================================
# InfluxDB Initialization Script
# ==============================================================================
# This script creates and starts the InfluxDB Docker container for the first
# time.
## ==============================================================================


# Storage and Container Details
FOLDER_ROOT_LOCATION="/path/to/docker/container/folder"
CONTAINER_NAME="tfds-fcd-influxdb-container"
# --- End of Configuration ---

# Check if a container with the same name already exists
if [ "$(docker ps -a -q -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Error: A container named '$CONTAINER_NAME' already exists."
    echo "If you need to re-initialize, please stop and remove the existing container first with remove_run_influxdb_docker_container.sh"
    exit 1
fi

# Define the data and config paths
DB_DATA="${FOLDER_ROOT_LOCATION}/data"
DB_CONFIG="${FOLDER_ROOT_LOCATION}/config"

# Create the directories if they don't exist
echo "Creating storage directories on external drive..."
mkdir -p "$DB_DATA"
mkdir -p "$DB_CONFIG"

# Run the Docker container with setup variables
echo "Starting InfluxDB container '$CONTAINER_NAME' for the first time..."
docker run \
  --name "$CONTAINER_NAME" \
  --detach \
  --user "$(id -u):$(id -g)" \
  -p 8086:8086 \
  -v "${DB_DATA}:/var/lib/influxdb2" \
  -v "${DB_CONFIG}:/etc/influxdb2" \
  influxdb:latest

echo "--------------------------------------------------------"
echo "InfluxDB container '$CONTAINER_NAME' started successfully! 🚀"
echo "Access UI at: http://localhost:8086"
echo ""
echo "--- Initial Setup Details ---"
echo "Organization: $INFLUXDB_ORG"
echo "Bucket:       $INFLUXDB_BUCKET"
echo "Username:     $INFLUXDB_USER"
echo ""
echo "Your Admin Token (SAVE THIS IN A PASSWORD MANAGER):"
echo "$INFLUXDB_TOKEN"
echo "--------------------------------------------------------"

#!/bin/sh
# Generate k8s/secrets.yaml from template with environment variable substitution
# Sets defaults for any unset variables

# Set defaults for InfluxDB (only if not already set)
export INFLUX_DB_ORG="${INFLUX_DB_ORG:-idea-helsinki}"
export INFLUX_DB_URL="${INFLUX_DB_URL:-http://influxdb:8086}"
export INFLUX_DB_FCD_BUCKET="${INFLUX_DB_FCD_BUCKET:-fcd-data}"
export INFLUX_DB_FCD_TOKEN="${INFLUX_DB_FCD_TOKEN:-dev-token-changeme}"
export INFLUX_DB_VALIDATION_BUCKET="${INFLUX_DB_VALIDATION_BUCKET:-validation}"
export INFLUX_DB_VALIDATION_TOKEN="${INFLUX_DB_VALIDATION_TOKEN:-dev-token-changeme}"
export SENTRY_DSN="${SENTRY_DSN:-}"

# Required variables (no defaults)
# AZURE_ACCOUNT_NAME, AZURE_CONTAINER_NAME, AZURE_SAS_TOKEN should come from .env

# Generate secrets.yaml
envsubst < k8s/secrets.yaml.tmpl > k8s/secrets.yaml

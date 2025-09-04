"""Private constants with environment variable support.

This module provides configuration values from environment variables
or falls back to default values for development.
"""

import os

# Azure account configuration
AZURE_ACCOUNT_NAME = os.getenv("AZURE_ACCOUNT_NAME", "account-name")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "container-name")
AZURE_SAS_TOKEN = os.getenv("AZURE_SAS_TOKEN", "super-secret-token")

# InfluxDB configuration
INFLUX_DB_ORG = os.getenv("INFLUX_DB_ORG", "TFDS")
INFLUX_DB_URL = os.getenv("INFLUX_DB_URL", "http://localhost:8086")

# FCD segment history bucket
INFLUX_DB_FCD_BUCKET = os.getenv("INFLUX_DB_FCD_BUCKET", "idea-fcd-bucket")
INFLUX_DB_FCD_TOKEN = os.getenv("INFLUX_DB_FCD_TOKEN", "super-secret-token")

# IDEA segment validation bucket
INFLUX_DB_VALIDATION_BUCKET = os.getenv("INFLUX_DB_VALIDATION_BUCKET", "idea-validation-bucket")
INFLUX_DB_VALIDATION_TOKEN = os.getenv("INFLUX_DB_VALIDATION_TOKEN", "another-super-secret-token")

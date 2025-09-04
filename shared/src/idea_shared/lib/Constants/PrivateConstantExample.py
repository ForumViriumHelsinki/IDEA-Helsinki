# ------------------------------------------------------#
# ------------------ CONSTANTS -------------------------#
# ------------------------------------------------------#

# This file contains constants that are sensitive in nature (keys, tokens, usernames, etc.)

# Azure account
AZURE_ACCOUNT_NAME = "account-name"
AZURE_CONTAINER_NAME = "container-name"
AZURE_SAS_TOKEN = "super-secret-token"

# FCD DB DEFAULTS
INFLUX_DB_ORG = "TFDS"
INFLUX_DB_URL = "http://localhost:8086"

# FCD segment history bucket
INFLUX_DB_FCD_BUCKET = "idea-fcd-bucket"
INFLUX_DB_FCD_TOKEN = "super-secret-token"  # In production, this should not be the same as the validation token

# IDEA segment validation bucket
INFLUX_DB_VALIDATION_BUCKET = "idea-validation-bucket"
INFLUX_DB_VALIDATION_TOKEN = "another-super-secret-token"  # In production, this should not be the same as the FCD token

#!/bin/zsh

# ==============================================================================
# InfluxDB script for deleting bucket contents
# ==============================================================================
# This script deletes ALL content from a given bucket, leaving it empty.
#
# WARNING: This action is permanent and cannot be undone.
# ==============================================================================

# --- Configuration ---
ORG_NAME="YOUR_ORG_NAME"
API_TOKEN="YOUR_API_TOKEN"
BUCKET_NAME="YOUR_BUCKET_NAME"
MEASUREMENT_TO_DROP="measurement to drop"

# --- Safety Confirmation ---
echo "WARNING: You are about to delete ALL data from the bucket '$BUCKET_NAME'."
echo "This action is irreversible."
# In zsh, 'read -q' waits for a single key press
read -q "REPLY?Press 'y' to continue, any other key to abort: "
echo # Move to the next line after the prompt

if [[ "$REPLY" != "y" ]]; then
    echo "Operation aborted by user."
    exit 1
fi

# --- Main Execution ---
echo "Proceeding with deletion..."

influx delete \
  --org "$ORG_NAME" \
  --token "$API_TOKEN" \
  --bucket "$BUCKET_NAME" \
  --start "1970-01-01T00:00:00Z" \
  --stop "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --predicate "_measurement=\"${MEASUREMENT_TO_DROP}\""

# --- Status Check ---
if [[ $? -eq 0 ]]; then
    echo "Successfully deleted all data from bucket '$BUCKET_NAME'."
else
    # Writing to stderr (>&2) is good practice for error messages
    echo "Error: Failed to delete data. Check your credentials and bucket name." >&2
    exit 1
fi

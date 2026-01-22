#!/bin/bash
# Startup script for Cloud Run
# Writes service account credentials from environment variable to file

set -e

# Create credentials directory if it doesn't exist
mkdir -p /app/credentials

# Write service account JSON to file if GCP_SA_KEY is set
if [ -n "$GCP_SA_KEY" ]; then
    echo "$GCP_SA_KEY" > /app/credentials/service-account.json
    chmod 600 /app/credentials/service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
    echo "Service account credentials written to /app/credentials/service-account.json"
fi

# Execute the main command
exec "$@"

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

# Use PORT from environment (Cloud Run sets this), default to 8080
export PORT=${PORT:-8080}
echo "Starting application on port $PORT"

# Replace --port argument in command if present
ARGS=()
SKIP_NEXT=false
for arg in "$@"; do
    if [ "$SKIP_NEXT" = true ]; then
        # Skip the port number after --port
        SKIP_NEXT=false
        continue
    elif [ "$arg" = "--port" ]; then
        # Replace --port with --port $PORT
        ARGS+=("--port")
        ARGS+=("$PORT")
        SKIP_NEXT=true
    else
        ARGS+=("$arg")
    fi
done

# Execute the command with updated port
exec "${ARGS[@]}"

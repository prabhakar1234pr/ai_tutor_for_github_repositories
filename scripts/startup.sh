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

# Extract app module from command arguments (e.g., "app.main:app" or "app.roadmap_service:app")
APP_MODULE=""
for arg in "$@"; do
    # Look for the app module (contains colon, like "app.main:app")
    if [[ "$arg" == *":"* ]] && [[ "$arg" != *"--"* ]] && [[ ! "$arg" =~ ^-- ]]; then
        APP_MODULE="$arg"
        break
    fi
done

# Default to main app if not found
if [ -z "$APP_MODULE" ]; then
    APP_MODULE="app.main:app"
fi

echo "Starting uvicorn with module: $APP_MODULE on port $PORT"

# Start uvicorn with the correct PORT (Cloud Run requirement)
exec uvicorn "$APP_MODULE" --host 0.0.0.0 --port "$PORT"

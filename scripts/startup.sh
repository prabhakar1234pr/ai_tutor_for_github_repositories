#!/bin/bash
# Startup script for Cloud Run
# Writes service account credentials from environment variable to file

# Don't exit on error immediately - we want to see what's happening
set -e

# Create credentials directory if it doesn't exist
mkdir -p /app/credentials

# Write service account JSON to file if GCP_SA_KEY is set
if [ -n "$GCP_SA_KEY" ]; then
    echo "$GCP_SA_KEY" > /app/credentials/service-account.json
    chmod 600 /app/credentials/service-account.json
    export GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
    echo "✓ Service account credentials written"
fi

# Use PORT from environment (Cloud Run sets this), default to 8080
# Cloud Run REQUIRES the app to listen on the PORT environment variable
export PORT=${PORT:-8080}
echo "✓ PORT environment variable: $PORT"

# Debug: Show all command arguments
echo "✓ Command arguments: $@"

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
    echo "⚠ App module not found in arguments, using default: $APP_MODULE"
fi

echo "✓ App module: $APP_MODULE"
echo "✓ Starting uvicorn on 0.0.0.0:$PORT"

# Verify uvicorn is available (try both direct command and python -m)
if command -v uvicorn &> /dev/null; then
    UVICORN_CMD="uvicorn"
elif python3 -m uvicorn --help &> /dev/null; then
    UVICORN_CMD="python3 -m uvicorn"
elif python -m uvicorn --help &> /dev/null; then
    UVICORN_CMD="python -m uvicorn"
else
    echo "✗ ERROR: uvicorn command not found!"
    echo "Trying to find Python:"
    which python3 || echo "python3 not found"
    which python || echo "python not found"
    echo "Trying to import uvicorn:"
    python3 -c "import uvicorn; print('uvicorn found')" || echo "uvicorn import failed"
    exit 1
fi

# Start uvicorn with the correct PORT (Cloud Run requirement)
# Use exec to replace shell process with uvicorn
echo "✓ Executing: $UVICORN_CMD $APP_MODULE --host 0.0.0.0 --port $PORT"
exec $UVICORN_CMD "$APP_MODULE" --host 0.0.0.0 --port "$PORT"

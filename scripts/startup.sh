#!/bin/bash
# Startup script for Cloud Run
# Writes service account credentials from environment variable to file

set -ex

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

# Use APP_MODULE from environment, default to main app
export APP_MODULE=${APP_MODULE:-app.main:app}

echo "✓ PORT: $PORT"
echo "✓ APP_MODULE: $APP_MODULE"

# Verify Python and uvicorn are available
echo "✓ Python version: $(python3 --version)"
if ! python3 -c "import uvicorn" 2>/dev/null; then
  echo "✗ ERROR: uvicorn not found in Python environment!"
  echo "Installed packages:"
  python3 -m pip list | grep -i uvicorn || echo "uvicorn not in pip list"
  exit 1
fi
echo "✓ uvicorn is available"

echo "✓ Starting $APP_MODULE on 0.0.0.0:$PORT"

# Start uvicorn using python3 -m (most reliable method)
# Use exec to replace shell process with uvicorn
# --workers 1 for Cloud Run (single-process friendly)
exec python3 -m uvicorn "$APP_MODULE" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1

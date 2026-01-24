#!/bin/bash
# Quick local development setup script

set -e

echo "🚀 GitGuide Local Development Setup"
echo "===================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "   Please create a .env file with your environment variables."
    echo "   See LOCAL_DEVELOPMENT.md for required variables."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if workspace image exists
if ! docker images | grep -q gitguide-workspace; then
    echo "📦 Building workspace base image..."
    docker build -t gitguide-workspace -f docker/Dockerfile.workspace .
    echo "✅ Workspace image built"
else
    echo "✅ Workspace image already exists"
fi

# Check if docker-compose.override.yml exists (for hot-reload)
if [ ! -f docker-compose.override.yml ]; then
    echo "📝 Creating docker-compose.override.yml for hot-reload..."
    cp docker-compose.override.yml.example docker-compose.override.yml
    echo "✅ Hot-reload enabled (edit files in app/ and see changes immediately)"
fi

# Check Docker socket access (for workspaces service)
if [ ! -S /var/run/docker.sock ]; then
    echo "⚠️  Warning: Docker socket not found at /var/run/docker.sock"
    echo "   Workspaces service may not work correctly."
fi

# Start services
echo ""
echo "🐳 Starting Docker Compose services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check service health
echo ""
echo "🏥 Checking service health..."

check_health() {
    local service=$1
    local url=$2
    local max_attempts=12
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "✅ $service is healthy"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts: $service not ready yet..."
        sleep 5
        attempt=$((attempt + 1))
    done

    echo "❌ $service failed to become healthy"
    return 1
}

check_health "API" "http://localhost:8000/api/health" || true
check_health "Roadmap" "http://localhost:8001/health" || true
check_health "Workspaces" "http://localhost:8002/health" || true

echo ""
echo "===================================="
echo "✅ Local development environment ready!"
echo ""
echo "Service URLs:"
echo "  📡 Main API:      http://localhost:8000"
echo "  🗺️  Roadmap:       http://localhost:8001"
echo "  💻 Workspaces:     http://localhost:8002"
echo ""
echo "Useful commands:"
echo "  📋 View logs:      docker-compose logs -f"
echo "  🛑 Stop services:  docker-compose down"
echo "  🔄 Restart:        docker-compose restart"
echo ""
echo "See LOCAL_DEVELOPMENT.md for more details."

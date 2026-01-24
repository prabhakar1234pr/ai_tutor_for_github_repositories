@echo off
REM Quick local development setup script for Windows

echo 🚀 GitGuide Local Development Setup
echo ====================================

REM Check if .env exists
if not exist .env (
    echo ⚠️  Warning: .env file not found!
    echo    Please create a .env file with your environment variables.
    echo    See LOCAL_DEVELOPMENT.md for required variables.
    pause
)

REM Check if workspace image exists
docker images | findstr gitguide-workspace >nul
if errorlevel 1 (
    echo 📦 Building workspace base image...
    docker build -t gitguide-workspace -f docker/Dockerfile.workspace .
    echo ✅ Workspace image built
) else (
    echo ✅ Workspace image already exists
)

REM Check if docker-compose.override.yml exists
if not exist docker-compose.override.yml (
    echo 📝 Creating docker-compose.override.yml for hot-reload...
    copy docker-compose.override.yml.example docker-compose.override.yml
    echo ✅ Hot-reload enabled
)

REM Start services
echo.
echo 🐳 Starting Docker Compose services...
docker-compose up -d

echo.
echo ⏳ Waiting for services to start...
timeout /t 5 /nobreak >nul

echo.
echo ====================================
echo ✅ Local development environment ready!
echo.
echo Service URLs:
echo   📡 Main API:      http://localhost:8000
echo   🗺️  Roadmap:       http://localhost:8001
echo   💻 Workspaces:     http://localhost:8002
echo.
echo Useful commands:
echo   📋 View logs:      docker-compose logs -f
echo   🛑 Stop services:  docker-compose down
echo   🔄 Restart:        docker-compose restart
echo.
echo See LOCAL_DEVELOPMENT.md for more details.
pause

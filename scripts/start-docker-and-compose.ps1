# Start Docker Desktop and wait for it to be ready, then run docker-compose

Write-Host "Checking Docker Desktop status..." -ForegroundColor Cyan

# Check if Docker is already running
$dockerRunning = docker info 2>&1 | Select-String -Pattern "Server:" -Quiet

if (-not $dockerRunning) {
    Write-Host "Docker Desktop is not running. Starting it..." -ForegroundColor Yellow

    # Try to start Docker Desktop
    $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerPath) {
        Start-Process $dockerPath
        Write-Host "Docker Desktop is starting. Please wait..." -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: Docker Desktop not found at $dockerPath" -ForegroundColor Red
        Write-Host "Please start Docker Desktop manually." -ForegroundColor Yellow
        exit 1
    }

    # Wait for Docker to be ready (max 60 seconds)
    $maxWait = 60
    $waited = 0
    Write-Host "Waiting for Docker to be ready..." -ForegroundColor Cyan

    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 2
        $waited += 2
        $dockerReady = docker info 2>&1 | Select-String -Pattern "Server:" -Quiet
        if ($dockerReady) {
            Write-Host "Docker Desktop is ready!" -ForegroundColor Green
            break
        }
        Write-Host "." -NoNewline -ForegroundColor Gray
    }

    if (-not $dockerReady) {
        Write-Host ""
        Write-Host "WARNING: Docker Desktop may still be starting. Please wait a bit longer." -ForegroundColor Yellow
        Write-Host "You can check status with: docker info" -ForegroundColor Yellow
    }
} else {
    Write-Host "Docker Desktop is already running!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Running docker-compose up -d..." -ForegroundColor Cyan
docker-compose up -d

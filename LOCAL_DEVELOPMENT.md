# Local Development Setup

This guide helps you run your GCP deployment structure locally for fast debugging without waiting for GitHub Actions workflows.

## Architecture

Your GCP deployment consists of:
- **2 Cloud Run services**: `gitguide-api` (main API) and `gitguide-roadmap` (roadmap generation)
- **1 VM**: `gitguide-workspaces` (Docker-based workspaces)

Locally, we mirror this with Docker Compose:
- **api** service → port 8000 (mirrors `gitguide-api` Cloud Run)
- **roadmap** service → port 8001 (mirrors `gitguide-roadmap` Cloud Run)
- **workspaces** service → port 8002 (mirrors `gitguide-workspaces` VM)

## Prerequisites

1. **Docker & Docker Compose** installed
2. **.env file** with your environment variables (see `.env.example`)
3. **Docker socket access** (for workspaces service to manage containers)

## Quick Start

### 1. Set up environment variables

Copy your `.env` file or create one with required variables:

```bash
# Required
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_service_key
DATABASE_URL=your_database_url
QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_key
CLERK_SECRET_KEY=your_clerk_key
JWT_SECRET=your_jwt_secret

# Optional (for local development)
ROADMAP_SERVICE_URL=http://roadmap:8080
INTERNAL_AUTH_TOKEN=dev-token
CORS_ORIGINS=*
```

### 2. Build workspace Docker image (one-time setup)

The workspaces service needs the workspace base image:

```bash
docker build -t gitguide-workspace -f docker/Dockerfile.workspace .
```

### 3. Start all services

```bash
docker-compose up -d
```

This starts all 3 services:
- API: http://localhost:8000
- Roadmap: http://localhost:8001
- Workspaces: http://localhost:8002

### 4. View logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f roadmap
docker-compose logs -f workspaces
```

### 5. Stop services

```bash
docker-compose down
```

## Development Workflow

### Hot Reload (Recommended)

For faster iteration, use volume mounts to enable hot-reload:

1. Copy `docker-compose.override.yml.example` to `docker-compose.override.yml`
2. This enables code changes to reflect immediately (no rebuild needed)

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
docker-compose up -d
```

Now when you edit files in `app/`, changes are reflected immediately.

### Rebuild after dependency changes

If you change `pyproject.toml` or Dockerfiles:

```bash
docker-compose build
docker-compose up -d
```

### Test individual services

```bash
# Test API health
curl http://localhost:8000/api/health

# Test Roadmap health
curl http://localhost:8001/health

# Test Workspaces health
curl http://localhost:8002/health
```

## Debugging Tips

### 1. Check service status

```bash
docker-compose ps
```

### 2. Execute commands in containers

```bash
# Shell into API container
docker-compose exec api bash

# Shell into Roadmap container
docker-compose exec roadmap bash

# Shell into Workspaces container
docker-compose exec workspaces bash
```

### 3. View real-time logs

```bash
# Follow logs for specific service
docker-compose logs -f --tail=100 api
```

### 4. Restart a single service

```bash
docker-compose restart api
docker-compose restart roadmap
docker-compose restart workspaces
```

### 5. Rebuild and restart a service

```bash
docker-compose up -d --build api
```

## Service URLs

| Service | Local URL | GCP Equivalent |
|---------|-----------|----------------|
| Main API | http://localhost:8000 | `gitguide-api` Cloud Run |
| Roadmap | http://localhost:8001 | `gitguide-roadmap` Cloud Run |
| Workspaces | http://localhost:8002 | `gitguide-workspaces` VM |

## Common Issues

### Workspaces service can't access Docker

**Error**: `Cannot connect to the Docker daemon`

**Solution**: Ensure Docker socket is accessible:
```bash
# On Linux/Mac
sudo chmod 666 /var/run/docker.sock

# Or add your user to docker group
sudo usermod -aG docker $USER
# Then logout and login again
```

### Port already in use

**Error**: `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Solution**: Change ports in `docker-compose.yml` or stop the conflicting service:
```bash
# Find what's using the port
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows
```

### Environment variables not loading

**Error**: Services start but can't connect to databases/APIs

**Solution**: Ensure `.env` file exists in project root and contains all required variables.

### Workspace containers fail to create

**Error**: Workspaces service can't create Docker containers

**Solution**:
1. Ensure workspace base image exists: `docker images | grep gitguide-workspace`
2. If missing, build it: `docker build -t gitguide-workspace -f docker/Dockerfile.workspace .`
3. Check Docker socket mount: `docker-compose exec workspaces ls -la /var/run/docker.sock`

## Comparison: Local vs GCP

| Aspect | Local (Docker Compose) | GCP |
|--------|------------------------|-----|
| **Startup time** | ~30 seconds | ~15 minutes (GitHub Actions) |
| **Debugging** | Instant logs, hot-reload | Check Cloud Run logs, redeploy |
| **Cost** | Free | Pay per use |
| **Scaling** | Single instance | Auto-scales 0-N instances |
| **Networking** | Docker bridge network | Cloud Run + VM networking |
| **Storage** | Local volumes | Cloud Run ephemeral + VM persistent |

## Next Steps

1. **Fix bugs locally** - Test changes immediately
2. **Verify locally** - Ensure everything works
3. **Push to GitHub** - Trigger GCP deployment only when ready
4. **Monitor GCP** - Check Cloud Run logs to verify production deployment

This setup gives you the best of both worlds: fast local iteration + production deployment!

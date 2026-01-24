# Local Development Setup - Summary

## What Was Created

I've set up a **local Docker Compose environment** that mirrors your GCP deployment structure, allowing you to:

✅ **Debug instantly** - No more 15-minute GitHub Actions waits
✅ **Test locally** - Same architecture as production (2 Cloud Run + 1 VM)
✅ **Hot-reload** - Code changes reflect immediately
✅ **Run alongside GCP** - Both can run simultaneously

## Files Created

1. **`docker-compose.yml`** - Main compose file with 3 services:
   - `api` (port 8000) → mirrors `gitguide-api` Cloud Run
   - `roadmap` (port 8001) → mirrors `gitguide-roadmap` Cloud Run
   - `workspaces` (port 8002) → mirrors `gitguide-workspaces` VM

2. **`docker-compose.override.yml.example`** - Template for hot-reload (auto-copied on first run)

3. **`LOCAL_DEVELOPMENT.md`** - Complete guide with troubleshooting

4. **`scripts/dev-local.sh`** - Quick setup script (Linux/Mac)

5. **`scripts/dev-local.bat`** - Quick setup script (Windows)

## Quick Start

### Option 1: Use the script (easiest)

**Windows:**
```powershell
.\scripts\dev-local.bat
```

**Linux/Mac:**
```bash
./scripts/dev-local.sh
```

### Option 2: Manual setup

```bash
# 1. Build workspace image (one-time)
docker build -t gitguide-workspace -f docker/Dockerfile.workspace .

# 2. Start all services
docker-compose up -d

# 3. Check logs
docker-compose logs -f
```

## Service URLs

| Service | Local URL | GCP Equivalent |
|---------|-----------|----------------|
| Main API | http://localhost:8000 | `gitguide-api` Cloud Run |
| Roadmap | http://localhost:8001 | `gitguide-roadmap` Cloud Run |
| Workspaces | http://localhost:8002 | `gitguide-workspaces` VM |

## Development Workflow

### Before (Slow 😞)
```
1. Find error in GCP logs
2. Fix code locally
3. Commit & push
4. Wait 15 minutes for GitHub Actions
5. Check if fixed
6. Repeat if not fixed
```

### Now (Fast 🚀)
```
1. Find error in GCP logs
2. Fix code locally
3. docker-compose restart api  (or just edit with hot-reload)
4. Test immediately (< 10 seconds)
5. Verify fix works
6. Commit & push (only when ready!)
```

## Key Features

### ✅ Hot Reload
With `docker-compose.override.yml`, code changes in `app/` are reflected immediately without rebuilding.

### ✅ Same Architecture
- Same service separation (API, Roadmap, Workspaces)
- Same environment variables
- Same Docker images (uses your Dockerfiles)

### ✅ Docker Socket Access
Workspaces service can create/manage containers just like the VM.

### ✅ Network Isolation
Services communicate via Docker network (same as GCP internal networking).

## Environment Variables

Your existing `.env` file works! The compose file loads all variables automatically.

Required variables (same as GCP):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `DATABASE_URL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `CLERK_SECRET_KEY`
- `JWT_SECRET`

Optional (for local):
- `ROADMAP_SERVICE_URL=http://roadmap:8080` (auto-set)
- `INTERNAL_AUTH_TOKEN=dev-token` (auto-set if not provided)
- `CORS_ORIGINS=*` (defaults to *)

## Troubleshooting

### Workspaces can't access Docker
**Windows:** Docker Desktop should handle this automatically
**Linux:** `sudo chmod 666 /var/run/docker.sock` or add user to docker group

### Port conflicts
Change ports in `docker-compose.yml` if 8000/8001/8002 are in use.

### Services won't start
Check logs: `docker-compose logs api` (or roadmap/workspaces)

## Next Steps

1. **Run the setup script** - `.\scripts\dev-local.bat` (Windows) or `./scripts/dev-local.sh` (Linux/Mac)
2. **Test locally** - Fix bugs and verify changes work
3. **Deploy to GCP** - Only push when you're confident it works!

## Benefits

- ⚡ **15 minutes → 10 seconds** feedback loop
- 🐛 **Instant debugging** - See errors immediately
- 💰 **Free** - No GCP costs for local testing
- 🔄 **Hot-reload** - Edit code, see changes instantly
- 🎯 **Same structure** - What works locally works in GCP

You can now debug locally and only deploy to GCP when you're confident everything works! 🎉

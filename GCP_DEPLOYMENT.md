# GCP Deployment Guide with GitHub Actions CI/CD

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GCP Project: gitguide-backend                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Cloud Run Services                           │   │
│  │  ┌─────────────────────────┐    ┌─────────────────────────┐         │   │
│  │  │   gitguide-api          │    │   gitguide-roadmap      │         │   │
│  │  │   (Main API)            │    │   (Roadmap Generation)  │         │   │
│  │  │   - 1 vCPU, 1Gi RAM     │    │   - 2 vCPU, 2Gi RAM     │         │   │
│  │  │   - Scale to 0          │    │   - Scale to 0          │         │   │
│  │  │   - Timeout: 300s       │    │   - Timeout: 900s       │         │   │
│  │  └─────────────────────────┘    └─────────────────────────┘         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Compute Engine VM                               │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │   gitguide-workspaces                                        │    │   │
│  │  │   - e2-small (2 vCPU, 2GB RAM)                              │    │   │
│  │  │   - 50GB SSD persistent disk                                 │    │   │
│  │  │   - Docker for user containers                               │    │   │
│  │  │   - WebSocket support for terminal                           │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Service Breakdown

### 1. Cloud Run: Main API (`gitguide-api`)

**Routes:**
- `/api/users/*` - User management
- `/api/projects/*` - Project CRUD
- `/api/roadmap/*` - Roadmap read operations
- `/api/chatbot/*` - RAG chatbot
- `/api/progress/*` - Progress tracking
- `/api/project_chunks_embeddings/*` - Embeddings
- `/api/github/*` - GitHub consent
- `/api/task-sessions/*` - Task sessions
- `/api/tasks/*` - Task verification

### 2. Cloud Run: Roadmap Generation (`gitguide-roadmap`)

**Routes:**
- `/api/roadmap/generate` - Trigger roadmap generation (LLM-heavy)

### 3. Compute Engine VM: Workspaces (`gitguide-workspaces`)

**Routes:**
- `/api/workspaces/*` - Workspace management
- `/api/terminal/*` - Terminal WebSocket
- `/api/files/*` - File operations
- `/api/preview/*` - Preview proxy
- `/api/git/*` - Git operations in containers

---

## GitHub Actions CI/CD

### Workflow: `.github/workflows/deploy.yml`

```yaml
name: Deploy to GCP

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  PROJECT_ID: gitguide-backend
  REGION: us-central1
  GAR_LOCATION: us-central1-docker.pkg.dev

jobs:
  # ============================================
  # Build and Deploy Cloud Run Services
  # ============================================
  deploy-cloud-run:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
        with:
          project_id: ${{ env.PROJECT_ID }}

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker ${{ env.REGION }}-docker.pkg.dev --quiet

      # Build and push main API image
      - name: Build Main API Image
        run: |
          docker build -t ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/api:${{ github.sha }} .
          docker push ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/api:${{ github.sha }}

      # Build and push roadmap service image
      - name: Build Roadmap Service Image
        run: |
          docker build -f Dockerfile.roadmap -t ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/roadmap:${{ github.sha }} .
          docker push ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/roadmap:${{ github.sha }}

      # Deploy Main API to Cloud Run
      - name: Deploy Main API to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: gitguide-api
          region: ${{ env.REGION }}
          image: ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/api:${{ github.sha }}
          flags: |
            --memory=1Gi
            --cpu=1
            --timeout=300
            --max-instances=10
            --min-instances=0
            --allow-unauthenticated

      # Deploy Roadmap Service to Cloud Run
      - name: Deploy Roadmap Service to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: gitguide-roadmap
          region: ${{ env.REGION }}
          image: ${{ env.GAR_LOCATION }}/${{ env.PROJECT_ID }}/gitguide/roadmap:${{ github.sha }}
          flags: |
            --memory=2Gi
            --cpu=2
            --timeout=900
            --max-instances=5
            --min-instances=0
            --no-allow-unauthenticated

  # ============================================
  # Deploy to Workspace VM
  # ============================================
  deploy-workspace-vm:
    runs-on: ubuntu-latest
    needs: deploy-cloud-run

    steps:
      - name: Deploy to Workspace VM via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VM_HOST }}
          username: ${{ secrets.VM_USER }}
          key: ${{ secrets.VM_SSH_KEY }}
          script: |
            cd /opt/gitguide-backend
            git pull origin main
            source .venv/bin/activate
            uv pip install -r pyproject.toml
            sudo systemctl restart gitguide-workspaces
            echo "Deployment complete!"
```

---

## Files to Create

### 1. `Dockerfile` (Main API)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv pip install --system -r pyproject.toml

# Copy application code
COPY app/ ./app/
COPY credentials/ ./credentials/

# Set environment variables
ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 2. `Dockerfile.roadmap` (Roadmap Service)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv pip install --system -r pyproject.toml

COPY app/ ./app/
COPY credentials/ ./credentials/

ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080

CMD ["uvicorn", "app.roadmap_service:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 3. `app/roadmap_service.py` (Roadmap Service Entrypoint)

```python
"""
Minimal FastAPI app for roadmap generation service.
Deployed separately on Cloud Run with higher resources.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.services.roadmap_generation import router as roadmap_gen_router

logging.basicConfig(level=settings.log_level)

app = FastAPI(title="GitGuide Roadmap Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(roadmap_gen_router, prefix="/api/roadmap", tags=["roadmap-generation"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "roadmap"}
```

### 4. `app/workspace_service.py` (Workspace Service Entrypoint)

```python
"""
Minimal FastAPI app for workspace-related routes.
Runs on Compute Engine VM with Docker access.
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.workspaces import router as workspaces_router
from app.api.terminal import router as terminal_router
from app.api.files import router as files_router
from app.api.preview import router as preview_router
from app.api.git import router as git_router
from app.config import settings

logging.basicConfig(level=settings.log_level)

app = FastAPI(title="GitGuide Workspaces Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces_router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(files_router, prefix="/api/workspaces", tags=["files"])
app.include_router(terminal_router, prefix="/api/terminal", tags=["terminal"])
app.include_router(preview_router, prefix="/api/preview", tags=["preview"])
app.include_router(git_router, prefix="/api/git", tags=["git"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "workspaces"}
```

---

## GitHub Secrets Required

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

| Secret Name | Description |
|-------------|-------------|
| `GCP_SA_KEY` | Service account JSON key (full contents of `gitguide-backend-5d3d36f67a0c.json`) |
| `VM_HOST` | External IP of your Compute Engine VM |
| `VM_USER` | SSH username (usually your GCP username) |
| `VM_SSH_KEY` | Private SSH key for VM access |

---

## Initial GCP Setup Commands

Run these commands once before first deployment:

```bash
# 1. Enable required APIs
gcloud services enable \
  run.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

# 2. Create Artifact Registry repository
gcloud artifacts repositories create gitguide \
  --repository-format=docker \
  --location=us-central1 \
  --description="GitGuide Docker images"

# 3. Create Compute Engine VM for workspaces
gcloud compute instances create gitguide-workspaces \
  --zone=us-central1-a \
  --machine-type=e2-small \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=http-server,https-server

# 4. Configure firewall for VM
gcloud compute firewall-rules create allow-gitguide-workspaces \
  --allow=tcp:8080,tcp:30001-30010 \
  --target-tags=http-server

# 5. Get VM external IP (for GitHub secret)
gcloud compute instances describe gitguide-workspaces \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

---

## VM Setup Script

SSH into the VM and run:

```bash
#!/bin/bash

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install Python 3.12
sudo apt-get install -y python3.12 python3.12-venv python3-pip

# Clone repository
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git gitguide-backend
sudo chown -R $USER:$USER gitguide-backend
cd gitguide-backend

# Setup Python environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -r pyproject.toml

# Build workspace Docker image
docker build -t gitguide-workspace -f docker/Dockerfile.workspace .

# Create .env file (copy your environment variables)
cp .env.example .env
nano .env  # Edit with your actual values

# Create systemd service
sudo tee /etc/systemd/system/gitguide-workspaces.service << 'EOF'
[Unit]
Description=GitGuide Workspaces Service
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/gitguide-backend
EnvironmentFile=/opt/gitguide-backend/.env
ExecStart=/opt/gitguide-backend/.venv/bin/uvicorn app.workspace_service:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gitguide-workspaces
sudo systemctl start gitguide-workspaces

# Verify service is running
sudo systemctl status gitguide-workspaces
```

---

## Cost Estimate

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| Cloud Run (API) | 1 vCPU, 1Gi, scale to 0 | ~$5-15 (pay per use) |
| Cloud Run (Roadmap) | 2 vCPU, 2Gi, scale to 0 | ~$10-30 (pay per use) |
| Compute Engine VM | e2-small, 50GB SSD | ~$18 (always on) |
| Artifact Registry | Docker images | ~$1-5 |
| **Total** | | **~$34-68/month** |

With $300 free credits: **5-9 months of operation**

---

## Deployment Flow

```
1. Push to main branch
        ↓
2. GitHub Actions triggered
        ↓
3. Build Docker images
        ↓
4. Push to Artifact Registry
        ↓
5. Deploy to Cloud Run (API + Roadmap)
        ↓
6. SSH to VM, pull code, restart service
        ↓
7. All services updated!
```

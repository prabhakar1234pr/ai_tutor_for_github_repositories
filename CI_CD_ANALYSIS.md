# CI/CD Analysis & Deployment

## Deployment Method: GitHub Actions (Single Source)

**GitHub Actions** is the single CI/CD pipeline. Cloud Build triggers should be **disabled** to avoid duplicate deployments.

### Disable Cloud Build Triggers (One-Time)

Run once after adopting GitHub Actions:

```bash
# From project root, with gcloud authenticated to gitguide-backend
chmod +x .github/scripts/disable-cloud-build-triggers.sh
./.github/scripts/disable-cloud-build-triggers.sh
```

Or manually:

```bash
gcloud builds triggers delete rmgpgab-gitguide-api-us-central1-prabhakar1234pr-ai-tutor-folwi --project=gitguide-backend --quiet
gcloud builds triggers delete rmgpgab-gitguide-roadmap-us-central1-prabhakar1234pr-ai-tutocvd --project=gitguide-backend --quiet
```

---

## Workflows

### 1. Deploy (`.github/workflows/deploy.yml`)

| Trigger | Behavior |
|--------|----------|
| **Push to `main`** | Run CI → Deploy Cloud Run → Health checks → Deploy VM |
| **Pull request to `main`** | Run CI only (no deploy) |
| **`workflow_dispatch`** | Same as push to main |

**Jobs:**

1. **`ci`** – Lint + test
   - Ruff check, Ruff format check
   - Pytest (excludes e2e: `test_roadmap_e2e`, `test_langgraph_migration_e2e`)

2. **`deploy-cloud-run`** (only on push to main)
   - Build and push API + Roadmap images
   - Deploy both to Cloud Run
   - Wait for revisions
   - **Health check (API):** `curl` `/api/health`
   - **Health check (Roadmap):** Verify latest revision status

3. **`deploy-workspace-vm`** (only on push to main, after Cloud Run)
   - SSH to VM, `git fetch` + `git reset --hard origin/main`
   - `uv sync`, restart `gitguide-workspaces`
   - **Health check:** `systemctl is-active gitguide-workspaces`

### 2. Rollback (`.github/workflows/rollback.yml`)

| Trigger | Input |
|--------|--------|
| **`workflow_dispatch`** | `service`: `api` or `roadmap` |

Routes 100% traffic to the **previous** Cloud Run revision for the chosen service.

---

## CI/CD Fixes Applied

| Issue | Fix |
|-------|-----|
| Dual deployment (Cloud Build + Actions) | Use Actions only; script to disable Cloud Build |
| No pre-deployment tests | `ci` job: ruff + pytest before deploy |
| No health checks | API `curl` `/api/health`; Roadmap revision check; VM `systemctl is-active` |
| No rollback | `rollback.yml` workflow |
| VM deploy not robust | `git fetch` + `reset --hard`, `uv sync`, then health check |
| Deploy on PRs | Deploy only on push to main; PRs run CI only |

---

## Required Secrets

- `GCP_SA_KEY` – GCP service account JSON (Artifact Registry, Cloud Run)
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL`
- `QDRANT_URL`, `QDRANT_API_KEY`
- `CLERK_SECRET_KEY`, `JWT_SECRET`
- `ROADMAP_SERVICE_URL`, `INTERNAL_AUTH_TOKEN`
- `VM_HOST`, `VM_USER`, `VM_SSH_KEY` – for workspace VM deploy
- `GROQ_API_KEY`, `GROQ_API_KEY2` (roadmap service)

---

## Verification Commands

```bash
# Service URLs
gcloud run services describe gitguide-api --region=us-central1 --format='value(status.url)'
gcloud run services describe gitguide-roadmap --region=us-central1 --format='value(status.url)'

# Revisions
gcloud run revisions list --service=gitguide-api --region=us-central1 --limit=3
gcloud run revisions list --service=gitguide-roadmap --region=us-central1 --limit=3

# IAM (roadmap invoker)
gcloud run services get-iam-policy gitguide-roadmap --region=us-central1
```

---

**Last Updated:** 2026-01-24
**Status:** GitHub Actions is the single CI/CD source; Cloud Build should be disabled.

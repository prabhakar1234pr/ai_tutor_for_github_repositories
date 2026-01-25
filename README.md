# GitGuide Backend (FastAPI)

Backend for **GitGuide** — an AI-powered platform that turns any GitHub repository into a **guided learning roadmap**, a **repo-aware chatbot**, and a **Docker-backed workspace** for hands-on practice.

## What’s in here

This backend is split into 3 services (dev runs them together via Docker Compose):

- **API service** (`app/main.py`) — user/projects/chat/progress APIs + orchestration
- **Roadmap service** (`app/roadmap_service.py`) — LLM-heavy LangGraph workflows for roadmap generation
- **Workspaces service** (`app/workspace_service.py`) — Docker-backed workspaces (files, terminal, git, preview)

## Core features

- **Repository → learning roadmap**: LangGraph-powered curriculum planning + content generation
- **RAG chatbot**: answers questions using repository context (Qdrant + chunk storage)
- **Embeddings pipeline**: chunk files, embed, store + search by `project_id`
- **Docker workspaces (Phase 0)**: isolated containers with real file system operations

## Tech stack (backend)

- **FastAPI** + **Uvicorn**
- **Supabase (Postgres)** for app data
- **Qdrant** for vector search
- **LangGraph / LangChain** for multi-step AI workflows
- **Docker** for per-project workspaces

## Local development

### Prerequisites

- Python 3.12+
- Docker Desktop
- `uv` (recommended)

### Run all backend services (recommended)

```bash
cd ai_tutor_for_github_repositories
docker-compose up -d
```

Ports:

- API: `http://localhost:8000`
- Roadmap: `http://localhost:8001`
- Workspaces: `http://localhost:8002`

### Run API directly (without Docker Compose)

```bash
cd ai_tutor_for_github_repositories
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Environment variables

Local env setup is documented in the repo root `LOCAL_SETUP.md`. Common keys:

- **Supabase**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `DATABASE_URL`
- **Qdrant**: `QDRANT_URL`, `QDRANT_API_KEY`
- **Auth**: `CLERK_SECRET_KEY`, `JWT_SECRET`
- **GitHub**: `GIT_ACCESS_TOKEN`
- **LLM**: `GEMINI_*` / `GROQ_API_KEY` / `AZURE_OPENAI_*`

## Useful endpoints

- API docs: `http://localhost:8000/docs`
- Health checks:
  - `GET http://localhost:8000/api/health`
  - `GET http://localhost:8001/health`
  - `GET http://localhost:8002/health`

## Code map (high level)

- `app/api/` — HTTP routes (projects, chatbot, roadmap, progress, etc.)
- `app/agents/` — LangGraph workflows + nodes for analysis/generation/judging
- `app/services/` — business logic (RAG, embeddings, Docker workspace mgmt, preview proxy, git/terminal)
- `app/core/` — infra clients (Supabase, Qdrant) + startup utilities

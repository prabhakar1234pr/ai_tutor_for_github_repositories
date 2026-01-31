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

<!-- achievement: yolo -->

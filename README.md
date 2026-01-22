# AI Tutor for GitHub Repositories

Backend API service that transforms GitHub repositories into personalized learning roadmaps using AI-powered analysis and RAG (Retrieval-Augmented Generation).

**🎯 Phase 0 Complete** - Docker-backed workspaces with real file system operations.

## Project Structure

```
app/
├── main.py                 # FastAPI application entry point
├── config.py              # Settings and environment configuration
│
├── api/                   # API route handlers
│   ├── routes.py          # General routes (health, hello)
│   ├── users.py           # User management endpoints
│   ├── projects.py        # Project CRUD operations
│   ├── chatbot.py         # Chatbot RAG endpoints
│   ├── roadmap.py         # Roadmap generation endpoints
│   ├── progress.py        # Learning progress tracking
│   ├── workspaces.py      # 🆕 Workspace lifecycle endpoints
│   ├── files.py           # 🆕 File system operations endpoints
│   └── project_chunks_embeddings.py  # Chunk/embedding management
│
├── agents/                # LangGraph agent workflows
│   ├── roadmap_agent.py   # Main roadmap generation graph orchestrator
│   ├── state.py           # Agent state type definitions
│   ├── prompts.py         # LLM prompts for content generation
│   ├── day0.py            # Day 0 content generation logic
│   └── nodes/             # Individual graph nodes
│       ├── fetch_context.py        # Fetch project context from DB
│       ├── analyze_repo.py         # Analyze repository structure
│       ├── plan_curriculum.py      # Generate curriculum plan
│       ├── generate_content.py     # Generate day/concept content
│       └── save_to_db.py           # Persist generated content
│
├── services/              # Business logic layer
│   ├── github_service.py          # GitHub API integration
│   ├── embedding_service.py       # Text embedding generation
│   ├── embedding_pipeline.py      # Batch embedding processing
│   ├── qdrant_service.py          # Vector database operations
│   ├── rag_pipeline.py            # RAG query processing
│   ├── roadmap_generation.py      # Roadmap orchestration
│   ├── chunk_storage.py           # Chunk storage in Supabase
│   ├── docker_client.py           # 🆕 Docker SDK wrapper (thread-safe)
│   ├── workspace_manager.py       # 🆕 Workspace lifecycle management
│   └── file_system.py             # 🆕 Container file operations
│
├── core/                  # Core infrastructure clients
│   ├── supabase_client.py # Supabase database client
│   └── qdrant_client.py   # Qdrant vector DB client
│
├── docker/                # 🆕 Docker configuration
│   └── Dockerfile.workspace  # Base image for user workspaces
│
└── utils/                 # Utility functions
    ├── clerk_auth.py      # Clerk authentication helpers
    ├── db_helpers.py      # Database query helpers
    ├── github_utils.py    # GitHub URL parsing/validation
    ├── text_chunking.py   # Text chunking strategies
    ├── json_parser.py     # JSON parsing utilities
    └── time_estimation.py # Time estimation helpers
```

## Architecture Overview

### Request Flow

1. **API Layer** (`app/api/`): FastAPI routes handle HTTP requests
   - Authentication via Clerk JWT tokens
   - Request validation and error handling
   - Delegates to services layer

2. **Services Layer** (`app/services/`): Core business logic
   - GitHub repository cloning and analysis
   - Text chunking and embedding generation
   - Vector search via Qdrant
   - RAG response generation using Groq/Azure OpenAI
   - **🆕 Docker container management for workspaces**
   - **🆕 File system operations inside containers**

3. **Agent Layer** (`app/agents/`): LangGraph workflows
   - Roadmap generation agent orchestrates multi-step content creation
   - State machine manages generation progress
   - Nodes execute specific tasks (analyze, generate, save)

4. **Data Layer** (`app/core/`): Database clients
   - Supabase: Relational data (projects, users, roadmaps, chunks, **workspaces**)
   - Qdrant: Vector embeddings for semantic search

### Key Components

**Roadmap Generation Agent** (`app/agents/roadmap_agent.py`):
- LangGraph state machine with conditional edges
- Flow: Fetch context → Analyze repo → Plan curriculum → Generate days → Save to DB
- Handles Day 0 (intro) and Days 1-N (concepts with subconcepts and tasks)

**RAG Pipeline** (`app/services/rag_pipeline.py`):
- Query embedding → Vector search → Context retrieval → LLM generation
- Filters chunks by project_id for project-specific responses
- Supports conversation history for context-aware chat

**Embedding Pipeline** (`app/services/embedding_pipeline.py`):
- Processes repository files in batches
- Chunks code/text with overlap
- Generates embeddings and stores in Qdrant
- Stores chunk metadata in Supabase

**🆕 Workspace System** (Phase 0):
- **DockerClient** (`app/services/docker_client.py`): Thread-safe Docker SDK wrapper
  - Container creation with resource limits (512MB RAM, 0.5 CPU)
  - Container lifecycle (start/stop/destroy)
  - Command execution with retry logic
- **WorkspaceManager** (`app/services/workspace_manager.py`): High-level orchestration
  - Creates container + DB record atomically
  - Manages workspace state transitions
  - Handles cleanup on destroy
- **FileSystemService** (`app/services/file_system.py`): Container file operations
  - List, read, write, create, delete, rename files
  - Base64 encoding for safe content transfer
  - Path sanitization for security

## API Endpoints

### Core APIs
- `/api/health` - Health check
- `/api/users/*` - User management
- `/api/projects/*` - Project CRUD operations
- `/api/chatbot/*` - RAG-based chatbot queries
- `/api/roadmap/*` - Roadmap generation and retrieval
- `/api/progress/*` - Learning progress tracking

### 🆕 Workspace APIs (Phase 0)
- `POST /api/workspaces/create` - Create new workspace container
- `GET /api/workspaces/{id}` - Get workspace details
- `GET /api/workspaces/project/{id}` - Get workspace by project
- `DELETE /api/workspaces/{id}` - Destroy workspace and container
- `POST /api/workspaces/{id}/start` - Start container
- `POST /api/workspaces/{id}/stop` - Stop container
- `GET /api/workspaces/{id}/status` - Get live container status

### 🆕 File System APIs (Phase 0)
- `GET /api/workspaces/{id}/files` - List directory contents
- `GET /api/workspaces/{id}/files/content` - Read file content
- `PUT /api/workspaces/{id}/files/content` - Write file content
- `POST /api/workspaces/{id}/files` - Create file or directory
- `DELETE /api/workspaces/{id}/files` - Delete file or directory
- `POST /api/workspaces/{id}/files/rename` - Rename/move file

## Configuration

Settings are managed in `app/config.py` via environment variables:
- Database: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- Vector DB: `QDRANT_URL`, `QDRANT_API_KEY`
- LLM: `GROQ_API_KEY` (dev) or `AZURE_OPENAI_KEY` (prod)
- Auth: `CLERK_SECRET_KEY`, `JWT_SECRET`
- GitHub: `GIT_ACCESS_TOKEN`

## Running the Application

### Prerequisites
- Python 3.11+
- Docker Desktop (for workspace containers)
- uv (Python package manager)

### Build Workspace Image (Required for Phase 0)
```bash
cd docker
docker build -t gitguide-workspace:latest -f Dockerfile.workspace .
```

### Start the Server
```bash
# Development
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Or use provided scripts
./run.sh      # Unix
run.bat       # Windows
```

## Testing

Tests are located in `tests/` directory:
- `test_api_routes.py` - API endpoint tests
- `test_rag_pipeline.py` - RAG functionality tests
- `test_embedding_pipeline.py` - Embedding generation tests
- `test_services/` - Service layer unit tests

Run tests:
```bash
pytest
```

## Navigation Guide

**To add a new API endpoint:**
1. Create route handler in `app/api/[feature].py`
2. Register router in `app/main.py`
3. Add tests in `tests/test_[feature]_api.py`

**To modify roadmap generation:**
1. Update agent nodes in `app/agents/nodes/`
2. Modify prompts in `app/agents/prompts.py`
3. Adjust graph flow in `app/agents/roadmap_agent.py`

**To change embedding strategy:**
1. Modify chunking logic in `app/utils/text_chunking.py`
2. Update embedding service in `app/services/embedding_service.py`
3. Adjust pipeline in `app/services/embedding_pipeline.py`

**To add a new service:**
1. Create service module in `app/services/[service].py`
2. Use singleton pattern for client initialization
3. Add configuration in `app/config.py` if needed

**🆕 To modify workspace behavior:**
1. Update container config in `app/services/docker_client.py`
2. Modify workspace logic in `app/services/workspace_manager.py`
3. Adjust file operations in `app/services/file_system.py`
4. Update Dockerfile in `docker/Dockerfile.workspace` for new tools

## Database Schema (Workspaces)

```sql
CREATE TABLE workspaces (
  workspace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES "User"(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(project_id) ON DELETE CASCADE,
  container_id TEXT,
  container_status TEXT DEFAULT 'created',
  container_image TEXT DEFAULT 'gitguide-workspace:latest',
  last_active_at TIMESTAMPTZ DEFAULT now(),
  session_state JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, project_id)
);
```

---

## Development Roadmap

- [x] **Phase 0**: Workspace Foundation (Docker + File System)
- [ ] **Phase 1**: Terminal & Real Execution (WebSocket + xterm.js)
- [ ] **Phase 2**: Git Integration (Clone, Commit, Push)
- [ ] **Phase 3**: Verification System (AI-powered task verification)

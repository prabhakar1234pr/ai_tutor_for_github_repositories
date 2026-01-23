# LangGraph Migration to Roadmap Service - Summary

## Overview

All LangGraph workflows have been migrated to run exclusively in the `gitguide-roadmap` Cloud Run service. The main `gitguide-api` service now acts as a lightweight orchestrator that delegates all heavy LLM/agent work to the roadmap service via HTTP.

## What Changed

### Architecture

**Before:**
- LangGraph workflows ran in both `gitguide-api` and `gitguide-roadmap`
- Direct function calls between services
- Incremental generation ran in main API container

**After:**
- **ALL** LangGraph workflows run **ONLY** in `gitguide-roadmap`
- Main API delegates via HTTP calls
- Clear separation: main API = lightweight, roadmap service = heavy LLM work

### Files Modified

1. **`app/config.py`**
   - Added `roadmap_service_url` configuration
   - Added `internal_auth_token` configuration

2. **`app/roadmap_service.py`**
   - Added internal auth middleware (`verify_internal_auth`)
   - Added `/api/roadmap/incremental-generate` endpoint (internal)
   - Added `/api/roadmap/generate-internal` endpoint (internal)
   - All LangGraph entrypoints now execute here

3. **`app/services/roadmap_client.py`** (NEW)
   - HTTP client for calling roadmap service from main API
   - `call_roadmap_service_incremental()` - for incremental generation
   - `call_roadmap_service_generate()` - for full roadmap generation
   - `call_roadmap_service_incremental_sync()` - sync wrapper for BackgroundTasks

4. **`app/api/progress.py`**
   - Replaced direct calls to `trigger_incremental_generation_sync`
   - Now calls `call_roadmap_service_incremental_sync()` via HTTP

5. **`app/services/embedding_pipeline.py`**
   - Replaced direct call to `run_roadmap_generation`
   - Now calls `call_roadmap_service_generate()` via HTTP

## LangGraph Workflows Now in Roadmap Service

All of these execute **ONLY** in `gitguide-roadmap`:

1. **Initial Roadmap Generation** (`/api/roadmap/generate`)
   - `analyze_repository` node
   - `extract_patterns_from_tests` node
   - `plan_and_save_curriculum` node
   - `generate_concept_content` node
   - `generate_tasks_with_tests` node
   - All other LangGraph nodes

2. **Incremental Concept Generation** (`/api/roadmap/incremental-generate`)
   - `build_memory_context` node
   - `generate_concept_content` node
   - `mark_concept_complete` node
   - Sliding window logic (n+2 ahead)

## Configuration Required

### Environment Variables

Both services need these environment variables:

#### `gitguide-api` (Main API)
```bash
ROADMAP_SERVICE_URL=https://gitguide-roadmap-xxx.run.app
INTERNAL_AUTH_TOKEN=<shared-secret-token>
```

#### `gitguide-roadmap` (Roadmap Service)
```bash
INTERNAL_AUTH_TOKEN=<same-shared-secret-token>
```

### Setting Up Internal Auth Token

Generate a secure random token (e.g., using `openssl`):
```bash
openssl rand -hex 32
```

Set this same token in **both** Cloud Run services:
- `gitguide-api`: `INTERNAL_AUTH_TOKEN`
- `gitguide-roadmap`: `INTERNAL_AUTH_TOKEN`

## API Endpoints

### Public Endpoints (Clerk Auth Required)

- `POST /api/roadmap/generate` - Trigger roadmap generation (user-facing)
  - Requires Clerk token
  - Validates user owns project
  - Delegates to LangGraph workflow in roadmap service

### Internal Endpoints (Service-to-Service Auth)

- `POST /api/roadmap/incremental-generate` - Incremental concept generation
  - Requires `X-Internal-Token` header
  - Called by main API when user completes a concept
  - Runs LangGraph incremental generation workflow

- `POST /api/roadmap/generate-internal` - Full roadmap generation (internal)
  - Requires `X-Internal-Token` header
  - Called by main API from embedding pipeline
  - Runs complete LangGraph workflow

## Deployment Checklist

- [ ] Set `ROADMAP_SERVICE_URL` in `gitguide-api` Cloud Run service
- [ ] Set `INTERNAL_AUTH_TOKEN` in both `gitguide-api` and `gitguide-roadmap`
- [ ] Verify `gitguide-roadmap` has all required dependencies (LangGraph, Gemini, etc.)
- [ ] Test incremental generation flow (complete a concept → verify HTTP call)
- [ ] Test full roadmap generation flow (create project → verify HTTP call)
- [ ] Monitor Cloud Run logs to confirm LangGraph logs appear only in `gitguide-roadmap`
- [ ] Verify main API logs show HTTP calls to roadmap service (not direct LangGraph calls)

## Verification

### Check LangGraph Logs Location

**Should appear in `gitguide-roadmap` logs:**
- "Starting Roadmap Generation Pipeline"
- "Analyzing repository..."
- "Planning curriculum..."
- "Generating concept content..."
- "Generating tasks..."

**Should NOT appear in `gitguide-api` logs:**
- Any LangGraph node execution logs
- Any direct calls to `run_roadmap_agent` or `run_incremental_concept_generation`

**Should appear in `gitguide-api` logs:**
- "Calling roadmap service for incremental generation"
- "Calling roadmap service for full generation"
- HTTP request/response logs

## Notes

- `get_day_0_content()` from `app.agents.day0` remains in main API (it's static content, not LangGraph)
- All other agent-related code is now isolated to roadmap service
- Main API is now lightweight and fast to cold-start
- Roadmap service handles all heavy LLM operations with appropriate resources (2 vCPU, 2Gi RAM)

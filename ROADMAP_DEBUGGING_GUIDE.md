# Roadmap Service Debugging Guide

## Comprehensive Logging Added

All roadmap-related code now has extensive logging to help debug issues. Logs are structured with clear markers for easy searching.

---

## Logging Locations

### 1. Main API (`gitguide-api`) Logs

**File:** `app/services/embedding_pipeline.py`

**Look for these log messages:**
```
📚 Step 8/8: Triggering roadmap generation for project_id={project_id}
📞 Scheduling HTTP call to roadmap service...
🌐 Service URL: {url}
✅ Async task created for roadmap generation
```

**If you see errors:**
- `❌ ROADMAP_SERVICE_URL NOT CONFIGURED!` → Check environment variable
- `❌ INTERNAL_AUTH_TOKEN NOT CONFIGURED!` → Check environment variable
- `❌ Roadmap service HTTP call failed` → Check HTTP error details

**File:** `app/services/roadmap_client.py`

**Look for these log messages:**
```
📞 CALLING ROADMAP SERVICE FOR FULL GENERATION
📡 Making HTTP POST request to: {url}
⏳ Waiting for roadmap service response...
📥 Received response: Status {code}
✅ ROADMAP SERVICE RESPONDED SUCCESSFULLY
```

**If you see errors:**
- `❌ HTTP ERROR CALLING ROADMAP SERVICE` → Check HTTP status and response body
- `❌ UNEXPECTED ERROR CALLING ROADMAP SERVICE` → Check error details

**File:** `app/api/progress.py`

**Look for these log messages:**
```
🔄 Triggering incremental generation after concept {concept_id} completion
```

---

### 2. Roadmap Service (`gitguide-roadmap`) Logs

**File:** `app/roadmap_service.py`

**Look for these log messages when request arrives:**
```
🚀 FULL ROADMAP GENERATION REQUEST RECEIVED
📦 Project ID: {project_id}
🔗 GitHub URL: {url}
📊 Skill Level: {level}
📅 Target Days: {days}
✅ FULL ROADMAP GENERATION TRIGGERED SUCCESSFULLY
```

**For incremental generation:**
```
🔄 INCREMENTAL GENERATION REQUEST RECEIVED
📦 Project ID: {project_id}
✅ INCREMENTAL GENERATION TRIGGERED SUCCESSFULLY
```

**If you see errors:**
- `❌ ERROR TRIGGERING ROADMAP GENERATION` → Check error details
- `⚠️  Invalid internal auth token attempt` → Token mismatch

**File:** `app/services/roadmap_generation.py`

**Look for these log messages during generation:**
```
🚀 Starting Roadmap Generation Pipeline
📦 Project ID: {project_id}
🔄 Calling run_roadmap_agent (LangGraph workflow)
📊 Roadmap agent returned result: success={bool}
✅ Gemini-Powered Roadmap Generation Completed Successfully
```

**For incremental generation:**
```
🔄 STARTING INCREMENTAL CONCEPT GENERATION
📊 Loading project data from Supabase...
✅ Project data loaded
🔄 Starting incremental generation loop...
🔄 Incremental generation iteration {n}/{max}
✅ INCREMENTAL GENERATION COMPLETED
```

**If you see errors:**
- `❌ CRITICAL ERROR IN ROADMAP GENERATION` → Check full stack trace
- `❌ CRITICAL ERROR IN INCREMENTAL CONCEPT GENERATION` → Check full stack trace

---

## Debugging "No Content Generated" Issue

### Step 1: Check Main API Logs

**In `gitguide-api` Cloud Run logs, search for:**
```
📚 Step 8/8: Triggering roadmap generation
```

**If you DON'T see this:**
- Embedding pipeline didn't complete
- Check embedding pipeline logs for errors

**If you DO see this, check for:**
```
📞 CALLING ROADMAP SERVICE FOR FULL GENERATION
```

**If you DON'T see this:**
- Configuration issue (ROADMAP_SERVICE_URL or INTERNAL_AUTH_TOKEN missing)
- Check for error: `❌ ROADMAP_SERVICE_URL NOT CONFIGURED!`

**If you DO see this, check for:**
```
✅ ROADMAP SERVICE RESPONDED SUCCESSFULLY
```

**If you DON'T see this:**
- HTTP call failed
- Check for: `❌ HTTP ERROR CALLING ROADMAP SERVICE`
- Look at response status and body in logs

---

### Step 2: Check Roadmap Service Logs

**In `gitguide-roadmap` Cloud Run logs, search for:**
```
🚀 FULL ROADMAP GENERATION REQUEST RECEIVED
```

**If you DON'T see this:**
- Request never reached roadmap service
- Check main API logs for HTTP errors
- Verify ROADMAP_SERVICE_URL is correct
- Verify INTERNAL_AUTH_TOKEN matches in both services

**If you DO see this, check for:**
```
✅ FULL ROADMAP GENERATION TRIGGERED SUCCESSFULLY
```

**If you DON'T see this:**
- Error in roadmap_service.py endpoint
- Check for: `❌ ERROR TRIGGERING ROADMAP GENERATION`

**If you DO see this, check for:**
```
🚀 Starting Roadmap Generation Pipeline
```

**If you DON'T see this:**
- Async task didn't start
- Check for errors in roadmap_service.py

**If you DO see this, check for:**
```
🔄 Calling run_roadmap_agent (LangGraph workflow)
```

**If you DON'T see this:**
- Error before calling roadmap agent
- Check for errors in run_roadmap_generation function

**If you DO see this, check for:**
```
📊 Roadmap agent returned result: success={bool}
```

**If success=False:**
- LangGraph workflow failed
- Check for: `❌ Gemini-Powered Roadmap Generation Failed`
- Look at error message in logs

---

### Step 3: Verify Configuration

**Check environment variables in both services:**

**Main API (`gitguide-api`):**
```bash
gcloud run services describe gitguide-api --region=us-central1 --format='value(spec.template.spec.containers[0].env)'
```

Look for:
- `ROADMAP_SERVICE_URL` - Should be: `https://gitguide-roadmap-xxxxx.run.app`
- `INTERNAL_AUTH_TOKEN` - Should be a long hex string

**Roadmap Service (`gitguide-roadmap`):**
```bash
gcloud run services describe gitguide-roadmap --region=us-central1 --format='value(spec.template.spec.containers[0].env)'
```

Look for:
- `INTERNAL_AUTH_TOKEN` - Should match the one in main API

---

### Step 4: Test HTTP Call Manually

**Test if the roadmap service endpoint is accessible:**

```bash
# Get the roadmap service URL
ROADMAP_URL=$(gcloud run services describe gitguide-roadmap --region=us-central1 --format='value(status.url)')

# Get the internal auth token (from GitHub secrets or Cloud Run env vars)
# Then test the endpoint:
curl -X POST "${ROADMAP_URL}/api/roadmap/generate-internal" \
  -H "X-Internal-Token: ${INTERNAL_AUTH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "YOUR_PROJECT_ID",
    "github_url": "https://github.com/user/repo",
    "skill_level": "beginner",
    "target_days": 7
  }'
```

**Expected response:**
```json
{
  "success": true,
  "message": "Roadmap generation started",
  "project_id": "YOUR_PROJECT_ID"
}
```

**If you get 403:**
- Internal auth token mismatch

**If you get 503:**
- INTERNAL_AUTH_TOKEN not configured in roadmap service

**If you get 404:**
- Wrong URL or endpoint path

---

## Common Issues & Solutions

### Issue 1: "No logs in roadmap service"

**Possible causes:**
1. Request never reached roadmap service
2. ROADMAP_SERVICE_URL is wrong
3. HTTP call is failing silently

**Solution:**
- Check main API logs for HTTP errors
- Verify ROADMAP_SERVICE_URL is correct
- Check if async task is being created

### Issue 2: "403 Forbidden" errors

**Possible causes:**
1. INTERNAL_AUTH_TOKEN mismatch between services
2. Token not set in one of the services

**Solution:**
- Verify both services have the same INTERNAL_AUTH_TOKEN
- Check GitHub secrets are set correctly
- Redeploy both services

### Issue 3: "Roadmap generation triggered but no content"

**Possible causes:**
1. LangGraph workflow is failing silently
2. Error in roadmap agent execution
3. Database write failures

**Solution:**
- Check roadmap service logs for: `❌ CRITICAL ERROR IN ROADMAP GENERATION`
- Check for errors in individual LangGraph nodes
- Verify Supabase connection in roadmap service

### Issue 4: "Async task created but nothing happens"

**Possible causes:**
1. Event loop not running
2. Task getting garbage collected
3. Exception in async task

**Solution:**
- Check roadmap service logs immediately after task creation
- Look for any exceptions in the async task
- Verify the task callback is logging errors

---

## Log Search Queries

### In Main API Logs (gitguide-api):

**Find all roadmap-related logs:**
```
roadmap
```

**Find HTTP calls:**
```
CALLING ROADMAP SERVICE
```

**Find errors:**
```
❌
```

**Find configuration issues:**
```
NOT CONFIGURED
```

### In Roadmap Service Logs (gitguide-roadmap):

**Find all generation requests:**
```
GENERATION REQUEST RECEIVED
```

**Find LangGraph execution:**
```
Starting Roadmap Generation Pipeline
run_roadmap_agent
```

**Find errors:**
```
❌ CRITICAL ERROR
```

**Find completion:**
```
✅.*Completed
```

---

## Quick Diagnostic Commands

### Check if services are configured:

```bash
# Main API
gcloud run services describe gitguide-api --region=us-central1 \
  --format='value(spec.template.spec.containers[0].env)' | grep -i roadmap

# Roadmap Service
gcloud run services describe gitguide-roadmap --region=us-central1 \
  --format='value(spec.template.spec.containers[0].env)' | grep -i internal
```

### Check recent logs:

```bash
# Main API - last 100 lines
gcloud run services logs read gitguide-api --region=us-central1 --limit=100

# Roadmap Service - last 100 lines
gcloud run services logs read gitguide-roadmap --region=us-central1 --limit=100
```

### Filter for roadmap-related logs:

```bash
# Main API
gcloud run services logs read gitguide-api --region=us-central1 --limit=500 | grep -i roadmap

# Roadmap Service
gcloud run services logs read gitguide-roadmap --region=us-central1 --limit=500 | grep -i "generation\|roadmap"
```

---

## Next Steps After Adding Logging

1. **Redeploy both services** with the new logging
2. **Create a new project** and watch the logs in real-time
3. **Follow the log trail:**
   - Start in main API logs → look for "Step 8/8"
   - Check for HTTP call logs
   - Switch to roadmap service logs → look for "REQUEST RECEIVED"
   - Follow the generation pipeline logs

4. **If workflow still doesn't trigger:**
   - Check the exact error message in logs
   - Verify configuration is correct
   - Test the HTTP endpoint manually

The comprehensive logging will show you exactly where the process is failing!

# Deployment Verification Checklist

## ✅ Environment Variables Verified

### Main API (`gitguide-api`)
- ✅ `ROADMAP_SERVICE_URL` = `https://gitguide-roadmap-qonfz7xtjq-uc.a.run.app`
- ✅ `INTERNAL_AUTH_TOKEN` = `44c97678a7d1673286272e9555ea1d9e6e7bec51bc6b3709d17f087097d70ddb`

### Roadmap Service (`gitguide-roadmap`)
- ✅ `INTERNAL_AUTH_TOKEN` = `44c97678a7d1673286272e9555ea1d9e6e7bec51bc6b3709d17f087097d70ddb` (matches main API)
- ✅ `GCP_PROJECT_ID` = `gitguide-backend`
- ✅ `GCP_LOCATION` = `us-central1`
- ⚠️  `GCP_SA_KEY` - **Will be added in next deployment** (needed for Vertex AI Gemini)

## 🔧 Changes Made

### 1. Added Comprehensive Logging
- ✅ `app/roadmap_service.py` - Detailed request/response logging
- ✅ `app/services/roadmap_generation.py` - LangGraph workflow logging
- ✅ `app/services/roadmap_client.py` - HTTP call logging with error details
- ✅ `app/services/embedding_pipeline.py` - Configuration validation and HTTP call logging

### 2. Fixed Deployment Configuration
- ✅ Added `GCP_SA_KEY` to roadmap service env vars in `deploy.yml`
- ✅ This enables Vertex AI Gemini authentication in roadmap service

### 3. Improved Error Handling
- ✅ Configuration validation before making HTTP calls
- ✅ Detailed error messages with context
- ✅ Proper exception handling in async tasks

## 🚀 Deployment Status

**Code pushed to GitHub:** ✅ `344d659`

**GitHub Actions will:**
1. Build Docker images for both services
2. Deploy to Cloud Run with updated environment variables
3. Add `GCP_SA_KEY` to roadmap service (for Vertex AI)

## 📋 Post-Deployment Verification Steps

### 1. Wait for GitHub Actions to Complete
Check: https://github.com/prabhakar1234pr/ai_tutor_for_github_repositories/actions

### 2. Verify Environment Variables After Deployment

```bash
# Check roadmap service has GCP_SA_KEY
gcloud run services describe gitguide-roadmap --region=us-central1 \
  --format='value(spec.template.spec.containers[0].env)' | grep GCP_SA_KEY
```

### 3. Test Roadmap Generation

1. Create a new project via the frontend
2. Watch the logs in real-time:

```bash
# Main API logs (in one terminal)
gcloud run services logs tail gitguide-api --region=us-central1

# Roadmap service logs (in another terminal)
gcloud run services logs tail gitguide-roadmap --region=us-central1
```

### 4. Look for These Log Messages

**In Main API:**
```
📚 Step 8/8: Triggering roadmap generation
📞 CALLING ROADMAP SERVICE FOR FULL GENERATION
✅ ROADMAP SERVICE RESPONDED SUCCESSFULLY
```

**In Roadmap Service:**
```
🚀 FULL ROADMAP GENERATION REQUEST RECEIVED
✅ FULL ROADMAP GENERATION TRIGGERED SUCCESSFULLY
🚀 Starting Roadmap Generation Pipeline
🔄 Calling run_roadmap_agent (LangGraph workflow)
✅ Gemini-Powered Roadmap Generation Completed Successfully
```

## 🔍 Troubleshooting

### If workflow doesn't trigger:

1. **Check Main API logs for:**
   - `❌ ROADMAP_SERVICE_URL NOT CONFIGURED!` → Env var missing
   - `❌ INTERNAL_AUTH_TOKEN NOT CONFIGURED!` → Env var missing
   - `❌ HTTP ERROR CALLING ROADMAP SERVICE` → Check HTTP status

2. **Check Roadmap Service logs for:**
   - `⚠️  Invalid internal auth token attempt` → Token mismatch
   - `❌ ERROR TRIGGERING ROADMAP GENERATION` → Check error details
   - `❌ CRITICAL ERROR IN ROADMAP GENERATION` → LangGraph workflow failed

3. **Verify GCP_SA_KEY is set:**
   ```bash
   gcloud run services describe gitguide-roadmap --region=us-central1 \
     --format='value(spec.template.spec.containers[0].env)' | grep GCP_SA_KEY
   ```

   If not set, the roadmap service won't be able to authenticate with Vertex AI.

## ✅ Expected Behavior

After deployment:

1. **User creates project** → Main API receives request
2. **Embedding pipeline runs** → Main API processes embeddings
3. **Step 8 triggers** → Main API calls roadmap service via HTTP
4. **Roadmap service receives request** → Validates auth, creates async task
5. **LangGraph workflow runs** → All nodes execute in roadmap service
6. **Content generated** → Written to Supabase
7. **User sees content** → Frontend reads from Supabase

All LangGraph work happens **ONLY** in roadmap service!

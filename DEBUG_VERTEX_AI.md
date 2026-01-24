# Debugging Vertex AI Embedding Model 404 Error

## Error
```
404 GET .../publishers/google/models/textembedding-gecko@003: Publisher Model not found.
```

## Possible Causes

### 1. Vertex AI API Not Enabled
The Vertex AI API must be enabled in your GCP project.

**Check:**
```bash
gcloud services list --enabled --project=gitguide-backend | grep aiplatform
```

**Enable if missing:**
```bash
gcloud services enable aiplatform.googleapis.com --project=gitguide-backend
```

### 2. Model Not Available in Region
The model might not be available in your configured region (`us-central1`).

**Check available models:**
```bash
gcloud ai models list --region=us-central1 --project=gitguide-backend
```

**Try different region:**
Update `.env`:
```env
GCP_LOCATION=us-east1
# or
GCP_LOCATION=us-west1
```

### 3. Service Account Permissions
Your service account needs proper IAM roles.

**Required roles:**
- `roles/aiplatform.user`
- `roles/ml.developer` (or `roles/aiplatform.admin`)

**Check:**
```bash
gcloud projects get-iam-policy gitguide-backend \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:gemini-api-service@gitguide-backend.iam.gserviceaccount.com"
```

**Grant permissions:**
```bash
gcloud projects add-iam-policy-binding gitguide-backend \
  --member="serviceAccount:gemini-api-service@gitguide-backend.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### 4. Model Name Format Issue
Try different model name formats:

**Option A:** Use without version
```env
EMBEDDING_MODEL_NAME=textembedding-gecko
```

**Option B:** Use full publisher path (if supported)
```env
EMBEDDING_MODEL_NAME=publishers/google/models/textembedding-gecko@003
```

**Option C:** Try newer model
```env
EMBEDDING_MODEL_NAME=text-embedding-005
```

### 5. Check Local vs GCP Differences

**Local (Docker):**
- Check `GOOGLE_APPLICATION_CREDENTIALS` is set correctly
- Check `GCP_PROJECT_ID` is set
- Check `GCP_LOCATION` matches GCP deployment

**GCP (Cloud Run):**
- Check service account has permissions
- Check Vertex AI API is enabled
- Check region supports the model

## Debugging Steps

1. **Check environment variables in container:**
```bash
docker-compose exec api env | grep -E "GCP|GOOGLE|EMBEDDING"
```

2. **Check logs for initialization:**
```bash
docker-compose logs api | grep -E "Vertex AI|embedding|GCP"
```

3. **Test Vertex AI connection:**
```bash
docker-compose exec api python -c "
import vertexai
from vertexai.language_models import TextEmbeddingModel
vertexai.init(project='gitguide-backend', location='us-central1')
model = TextEmbeddingModel.from_pretrained('textembedding-gecko@003')
print('Success!')
"
```

4. **Compare with GCP:**
Check your GCP Cloud Run logs to see if the same error occurs there.

## Quick Test

Add this to your `.env` to see detailed Vertex AI logs:
```env
LOG_LEVEL=DEBUG
```

Then check logs:
```bash
docker-compose logs -f api | grep -i vertex
```

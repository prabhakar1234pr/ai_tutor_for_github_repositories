# Setup Vertex AI API for Gemini

Follow these steps to enable Vertex AI API and grant permissions to your service account.

## Step 1: Enable Vertex AI API

### Option A: Via GCP Console (Easiest)

1. Go to: https://console.cloud.google.com/apis/library/aiplatform.googleapis.com
2. Make sure project `gitguide-backend` is selected (top dropdown)
3. Click **"Enable"** button
4. Wait 1-2 minutes for activation

### Option B: Via gcloud CLI

```bash
gcloud services enable aiplatform.googleapis.com --project gitguide-backend
```

## Step 2: Grant Service Account Permissions

Your service account needs the `Vertex AI User` role to access Gemini models.

### Option A: Via GCP Console

1. Go to: https://console.cloud.google.com/iam-admin/iam?project=gitguide-backend
2. Find your service account: `gemini-api-service@gitguide-backend.iam.gserviceaccount.com`
3. Click the **pencil icon** (Edit) next to it
4. Click **"Add Another Role"**
5. Select: **"Vertex AI User"** (`roles/aiplatform.user`)
6. Click **"Save"**

### Option B: Via gcloud CLI

```bash
gcloud projects add-iam-policy-binding gitguide-backend \
    --member="serviceAccount:gemini-api-service@gitguide-backend.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

## Step 3: Verify Setup

After enabling the API and granting permissions:

1. Restart your backend server
2. Try the chatbot again
3. Check logs - you should see successful Gemini responses

## Troubleshooting

### Still getting 404 errors?

1. **Check API is enabled:**
   - Go to: https://console.cloud.google.com/apis/library/aiplatform.googleapis.com
   - Should show "API enabled" (green checkmark)

2. **Check service account permissions:**
   - Go to: https://console.cloud.google.com/iam-admin/iam?project=gitguide-backend
   - Find `gemini-api-service@gitguide-backend.iam.gserviceaccount.com`
   - Should have `Vertex AI User` role

3. **Check billing:**
   - Make sure billing is enabled (required for Vertex AI API)
   - Go to: https://console.cloud.google.com/billing

4. **Try a different region:**
   - Some models might not be available in all regions
   - Try changing `GCP_LOCATION` in `.env` to `us-east1` or `us-west1`

### Alternative: Use Direct API Key Method

If Vertex AI continues to have issues, you can use the direct API key method:

1. Get API key from: https://makersuite.google.com/app/apikey
2. Add to `.env`: `GEMINI_API_KEY=your-api-key-here`
3. Remove or comment out: `GOOGLE_APPLICATION_CREDENTIALS`
4. Restart server

This method won't use your GCP free credits, but will work immediately.
